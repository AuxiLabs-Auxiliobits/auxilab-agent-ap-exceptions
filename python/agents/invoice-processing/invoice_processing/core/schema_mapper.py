"""
Schema Mapper

Uses Gemini Pro to automatically map custom CSV headers to the canonical AP exception queue schema.
"""

import json
import logging
import re
import time

from .config import (
    get_llm_call_delay,
    get_llm_model,
)

logger = logging.getLogger("APException.SchemaMapper")

# The required canonical schema for the AP Exception Queue
CANONICAL_SCHEMA = [
    "invoice_id",
    "invoice_number",
    "invoice_date",
    "vendor_name",
    "po_number",
    "invoice_amount",
    "tax_amount",
    "currency",
    "exception_type",
    "exception_description",
    "days_outstanding",
    "approver_assigned"
]

_MAPPING_SYSTEM_PROMPT = """\
You are an expert Accounts Payable Data Engineer.
Your job is to map custom/raw CSV headers from a user's file into the standard canonical schema used by the AP Exception Handling system.

=== CANONICAL SCHEMA ===
The system REQUIRES the following exact keys:
1. "invoice_id" (The unique identifier for the invoice)
2. "invoice_number" (The actual invoice number provided by the vendor)
3. "invoice_date" (The date of the invoice)
4. "vendor_name" (The name of the supplier/vendor)
5. "po_number" (The Purchase Order number)
6. "invoice_amount" (The total amount of the invoice)
7. "tax_amount" (The tax amount of the invoice)
8. "currency" (The currency of the invoice)
9. "exception_type" (A short category like 'Price Variance', 'Missing PO', etc.)
10. "exception_description" (The detailed description of the issue)
11. "days_outstanding" (The age of the invoice in days)
12. "approver_assigned" (The name of the person assigned to approve/review)

=== INSTRUCTIONS ===
1. I will provide a list of raw headers from a CSV file.
2. You must return a JSON dictionary mapping the raw header (key) to the BEST MATCHING canonical schema field (value).
3. If a raw header has no obvious match in the canonical schema, leave its value as null or omit it.
4. EVERY canonical field must be mapped to exactly one raw header if possible. Do your best to infer meaning (e.g. "Supplier" -> "vendor_name", "Total_Due" -> "invoice_amount", "InvoiceNumber" -> "invoice_number").

=== OUTPUT FORMAT ===
Return ONLY a valid JSON dictionary mapping the raw headers to the canonical headers. No markdown fences. Start with { end with }.
Example:
{
  "InvoiceID": "invoice_id",
  "InvoiceNumber": "invoice_number",
  "Supplier": "vendor_name",
  "Total": "invoice_amount",
  ...
}
"""

# ---------------------------------------------------------------------------
# LLM Client — delegates to shared provider abstraction (Gemini or Claude)
# ---------------------------------------------------------------------------
from .llm_client import SharedLLMClient as _LLMClientShared  # noqa: E402


class _LLMClient:
    """Thin wrapper kept for call-site compatibility — delegates to SharedLLMClient."""

    @classmethod
    def generate(cls, prompt: str) -> tuple[str, float]:
        """Call the active LLM provider and return (response_text, latency_ms)."""
        return _LLMClientShared.generate(prompt)

def _extract_json_object(text: str) -> str:
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found")
    brace_count = 0
    end = -1
    for i in range(start, len(text)):
        if text[i] == "{":
            brace_count += 1
        elif text[i] == "}":
            brace_count -= 1
            if brace_count == 0:
                end = i + 1
                break
    if end == -1:
        raise ValueError("Unclosed JSON object")
    return text[start:end]

class SchemaMapper:
    """Uses Gemini to map arbitrary headers to the canonical schema."""
    
    def map_headers(self, raw_headers: list[str]) -> dict:
        """
        Maps a list of raw headers to the canonical schema.
        Returns a dict: {raw_header: canonical_header}
        """
        if not raw_headers:
            return {}
            
        # Optimization: If the raw headers perfectly match the canonical schema, skip the LLM call.
        if set(raw_headers).intersection(set(CANONICAL_SCHEMA)) == set(CANONICAL_SCHEMA):
            logger.info("Headers perfectly match canonical schema. Skipping AI mapping.")
            return {h: h for h in raw_headers}
            
        prompt = _MAPPING_SYSTEM_PROMPT + f"\n\nRAW HEADERS:\n{json.dumps(raw_headers)}"
        
        try:
            logger.info(f"Using AI Schema Mapper for headers: {raw_headers}")
            response_text, latency = _LLMClient.generate(prompt)
            
            # Clean up the response
            clean = response_text
            if clean.startswith("```"):
                lines = clean.split("\n")
                lines = [l for l in lines if not l.startswith("```")]
                clean = "\n".join(lines).strip()
                
            json_str = _extract_json_object(clean)
            json_str = re.sub(r",(\\s*[}\\]])", r"\\1", json_str)
            mapping = json.loads(json_str)
            
            logger.info(f"Schema mapping complete ({latency:.0f}ms): {mapping}")
            return mapping
        except Exception as e:
            logger.warning(f"AI Schema Mapping failed: {e}. Falling back to 1:1 mapping.")
            # Fallback to direct mapping (which will likely fail downstream if headers are wrong)
            return {h: h for h in raw_headers}
