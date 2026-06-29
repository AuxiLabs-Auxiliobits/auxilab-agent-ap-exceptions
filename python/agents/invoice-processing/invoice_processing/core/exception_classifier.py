"""
Exception Classifier

Uses Gemini Pro to classify each AP exception with:
  - primary_type  (canonical exception category)
  - root_cause_hypothesis (1-2 sentence analysis)
  - severity      (High / Medium / Low)
  - confidence    (0.0 - 1.0)
  - recommended_action (short human-readable next step)

Follows the same _LLMClient pattern as rule_discoverer.py.
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Literal

from .config import (
    get_llm_call_delay,
    get_llm_location,
    get_llm_model,
    get_llm_project_id,
)

logger = logging.getLogger("APException.Classifier")

# ---------------------------------------------------------------------------
# Valid exception types (canonical)
# ---------------------------------------------------------------------------

EXCEPTION_TYPES = [
    "Amount Exceeds Tolerance",
    "Exact Duplicate Invoice",
    "Potential Duplicate Invoice",
    "PO Not Found",
    "GRN Not Received",
    "Vendor Mismatch",
    "Currency Mismatch",
    "Future Date",
    "Missing Required Data",
    "VALID",
    "Unknown",
    "Other",
]

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ExceptionClassification:
    """Structured classification result for a single AP exception."""

    invoice_id: str = ""
    primary_type: str = "Other"
    root_cause_hypothesis: str = ""
    recommended_action: str = ""
    evidence_used: str = ""
    business_rule_triggered: str = ""
    missing_data: list[str] = field(default_factory=list)
    evidence_checked: str = ""
    raw_exception_type: str = ""
    llm_latency_ms: float = 0.0
    success: bool = False
    error: str = ""
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# LLM Client (same lazy-init pattern as rule_discoverer.py)
# ---------------------------------------------------------------------------


class _LLMClient:
    """Lazy-initialized Vertex AI Gemini Pro client."""

    _model = None

    @classmethod
    def get_model(cls):
        if cls._model is None:
            from google.cloud import aiplatform  # noqa: PLC0415
            from vertexai.generative_models import GenerativeModel  # noqa: PLC0415

            project_id = get_llm_project_id()
            if not project_id:
                raise ValueError(
                    "PROJECT_ID not set. Export it or add to .env file."
                )
            aiplatform.init(project=project_id, location=get_llm_location())
            cls._model = GenerativeModel(get_llm_model())
            logger.info(
                f"Initialized {get_llm_model()} for exception classification "
                f"(project={project_id})"
            )
        return cls._model

    @classmethod
    def generate(cls, prompt: str, max_retries: int = 5) -> tuple[str, float]:
        """Call Gemini Pro and return (response_text, latency_ms)."""
        model = cls.get_model()
        for attempt in range(max_retries):
            try:
                start = time.time()
                response = model.generate_content(prompt)
                latency_ms = (time.time() - start) * 1000
                call_delay = get_llm_call_delay()
                if call_delay > 0:
                    time.sleep(call_delay)
                return response.text.strip(), latency_ms
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "resource exhausted" in err_str or "quota" in err_str:
                    if attempt < max_retries - 1:
                        backoff = (2 ** attempt) + 2  # 3s, 4s, 6s, 10s
                        logger.warning(f"Rate limit hit (429). Retrying in {backoff}s (Attempt {attempt+1}/{max_retries})")
                        time.sleep(backoff)
                        continue
                raise


# ---------------------------------------------------------------------------
# JSON helpers (mirrors rule_discoverer.py)
# ---------------------------------------------------------------------------


def _strip_markdown_fences(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.split("\n")
    json_lines = []
    in_block = False
    for line in lines:
        if line.strip().startswith("```"):
            if in_block:
                break
            in_block = True
            continue
        elif in_block:
            json_lines.append(line)
    return "\n".join(json_lines).strip() if json_lines else text


def _extract_json_array(text: str) -> str:
    start = text.find("[")
    if start == -1:
        raise ValueError("No JSON array found in LLM response")
    bracket_count = 0
    end = -1
    for i in range(start, len(text)):
        if text[i] == "[":
            bracket_count += 1
        elif text[i] == "]":
            bracket_count -= 1
            if bracket_count == 0:
                end = i + 1
                break
    if end == -1:
        raise ValueError("Unclosed JSON array in LLM response")
    return text[start:end]


def _parse_json_response(text: str) -> list[dict]:
    clean = _strip_markdown_fences(text.strip())
    json_str = _extract_json_array(clean)
    json_str = re.sub(r",(\s*[}\]])", r"\1", json_str)
    return json.loads(json_str)


# ---------------------------------------------------------------------------
# Classification Prompt
# ---------------------------------------------------------------------------

_CLASSIFICATION_SYSTEM_PROMPT = """\
You are an expert Accounts Payable analyst. Your job is to classify AP invoice
exceptions using strict evidence-based reasoning. You must determine the root cause
and specific business rules violated by cross-referencing the Invoice Data with
the provided ERP Database and Phase 1 Master Rules.

=== EXCEPTION TYPES & LOGIC ===
- PO Not Found: Purchase Order number from invoice is blank, empty, or does not exist in the ERP purchase_orders database.
- Amount Exceeds Tolerance: Invoice amount differs from the expected amount for that PO in the ERP purchase_orders database.
- GRN Not Received: A valid PO exists but there is no GRN record, or the GRN record says received=false.
- Vendor Mismatch: The vendor_name from the invoice is not in the ERP vendor_master list, OR the invoice vendor_name does not match the vendor_name associated with the PO in the ERP purchase_orders database.
- Exact Duplicate Invoice: The exact same vendor_name AND invoice_number AND invoice_amount exist in the ERP historical_invoices.
- Potential Duplicate Invoice: The exact same vendor_name AND invoice_number exist in the ERP historical_invoices, BUT the invoice_amount is DIFFERENT. This could be a corrected invoice or revision.
- Currency Mismatch: The currency on the invoice does not match the expected_currency on the PO in the ERP database.
- Future Date: The invoice_date is in the future compared to the provided processing_date.
- Missing Required Data: The invoice is missing a required non-PO field (e.g. invoice_number, vendor_name, invoice_amount, currency) or the field has a default 'UNKNOWN' value indicating missing data. Do NOT use this for a missing PO number; use 'PO Not Found' instead.
- VALID: If ALL validation checks pass, the invoice amount and currency are correct, it is not a duplicate, the PO exists, GRN is received, vendor matches, and no other exceptions or missing data exist.
- Unknown: Only use this when there is insufficient data to evaluate rules, evidence is contradictory, or required reference data is missing. NEVER use this when all checks pass.
- Other: Only use this if there is a clear violation that does NOT fit ANY of the above categories. Do not use this for Vendor Mismatch, Missing Data, or Future Date.

=== STRICT EVIDENCE RULES ===
DO NOT guess. Provide clear evidence for every classification. If there is insufficient data, use 'Unknown' and list the missing data.
For duplicate invoices, always state the incoming invoice amount vs the historical invoice amount in the evidence.

=== OUTPUT FORMAT ===
Return a JSON array of objects. An invoice can have MULTIPLE exceptions simultaneously. For each exception found, include:
[
  {
    "primary_type": "<one of the exception types above>",
    "root_cause_hypothesis": "<1-2 sentence analysis of why this exception occurred>",
    "evidence_used": "<Specific fields/values from the ERP database and invoice used to deduce this. Make sure to include amounts for duplicates.>",
    "evidence_checked": "<What data you looked at to conclude this>",
    "missing_data": ["<list>", "<of>", "<missing>", "<sources>"],
    "business_rule_triggered": "<The specific rule violated>",
    "recommended_action": "<short actionable next step for the AP team>"
  }
]

Return ONLY a valid JSON array. No markdown. No explanation.
"""

_CLASSIFICATION_TASK_TEMPLATE = """\
=== PROCESSING DATE ===
{processing_date}

=== RAW INVOICE DATA ===
{invoice_json}

=== ERP DATABASE CONTEXT ===
{erp_context}

=== PHASE 1 MASTER RULES ===
{master_rules}

Analyze the raw invoice data against the ERP context and master rules.
Return the JSON array of all exceptions discovered.
"""


# ---------------------------------------------------------------------------
# Main Classifier
# ---------------------------------------------------------------------------


class ExceptionClassifier:
    """
    Classifies AP exceptions using Gemini Pro.
    """

    def classify_one(self, exception: dict, erp_context: dict, master_rules: dict) -> list[ExceptionClassification]:
        """
        Classify a single exception dict and return a list of classifications.
        """
        invoice_id = exception.get("invoice_id", "UNKNOWN")
        raw_exception_type = exception.get("exception_type", "")
        
        from datetime import datetime
        prompt = (
            _CLASSIFICATION_SYSTEM_PROMPT
            + "\n\n"
            + _CLASSIFICATION_TASK_TEMPLATE.format(
                processing_date=erp_context.get("processing_date", datetime.now().strftime("%Y-%m-%d")),
                invoice_json=json.dumps(exception, indent=2),
                erp_context=json.dumps(erp_context, indent=2),
                master_rules=json.dumps(master_rules, indent=2),
            )
        )

        try:
            response_text, latency_ms = _LLMClient.generate(prompt)
            parsed_list = _parse_json_response(response_text)
            
            results = []
            for parsed in parsed_list:
                result = ExceptionClassification(
                    invoice_id=invoice_id,
                    raw_exception_type=raw_exception_type,
                    llm_latency_ms=latency_ms,
                    success=True
                )

                # Validate and normalise primary_type
                primary_type = parsed.get("primary_type", "Other")
                if primary_type not in EXCEPTION_TYPES and primary_type != "Unknown":
                    primary_type = "Other"

                result.primary_type = primary_type
                result.root_cause_hypothesis = parsed.get("root_cause_hypothesis", "")
                result.recommended_action = parsed.get("recommended_action", "")
                result.evidence_used = parsed.get("evidence_used", "")
                result.evidence_checked = parsed.get("evidence_checked", "")
                result.missing_data = parsed.get("missing_data", [])
                result.business_rule_triggered = parsed.get("business_rule_triggered", "")
                if "confidence" in parsed:
                    result.confidence = float(parsed["confidence"])

                logger.info(
                    f"  [{result.invoice_id}] → {primary_type} "
                    f"({latency_ms:.0f}ms)"
                )
                results.append(result)
                
            return results

        except Exception as e:
            logger.warning(f"  [{invoice_id}] classification failed: {e}")
            result = ExceptionClassification(
                invoice_id=invoice_id,
                raw_exception_type=raw_exception_type,
                success=False,
                error=str(e)
            )
            raw = exception.get("exception_type", "Other")
            result.primary_type = raw if raw in EXCEPTION_TYPES else "Other"
            result.root_cause_hypothesis = (
                f"Classification failed — using raw type '{raw}'. Error: {e}"
            )
            result.recommended_action = "Manual review required."
            return [result]

    def classify_batch(
        self, exceptions: list[dict], erp_context: dict = None, master_rules: dict = None
    ) -> list[ExceptionClassification]:
        """
        Classify a list of exception dicts.

        Args:
            exceptions: List of exception dicts.
            erp_context: Mock ERP database context.
            master_rules: Phase 1 master rules.

        Returns:
            Flattened list of ExceptionClassification results.
        """
        if erp_context is None:
            erp_context = {}
        if master_rules is None:
            master_rules = {}
            
        results = []
        total = len(exceptions)
        logger.info(f"Classifying {total} exceptions...")

        for i, exc in enumerate(exceptions, 1):
            invoice_id = exc.get("invoice_id", f"row-{i}")
            logger.info(f"  Classifying {i}/{total}: {invoice_id}")
            classifications = self.classify_one(exc, erp_context, master_rules)
            results.extend(classifications)

        success_count = sum(1 for r in results if r.success)
        logger.info(
            f"Classification complete: {success_count}/{len(results)} individual exceptions successfully identified"
        )
        return results
