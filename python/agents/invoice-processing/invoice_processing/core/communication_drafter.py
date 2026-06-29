"""
Communication Drafter

Uses Gemini Pro to draft the appropriate communication for each AP exception
that requires outreach. Five communication types, each with a dedicated
prompt template.

Communication types:
  1. vendor_query          — Price Variance / Quantity Mismatch
  2. internal_po_request   — Missing PO → requestor
  3. escalation_note       — High-value / high-variance → Finance Controller
  4. duplicate_hold        — Duplicate → hold notification
  5. unapproved_vendor     — Unapproved Vendor → Procurement team
"""

import logging
import time

from .config import (
    get_llm_call_delay,
    get_llm_location,
    get_llm_model,
    get_llm_project_id,
)

logger = logging.getLogger("APException.Drafter")

# ---------------------------------------------------------------------------
# Communication prompt templates
# ---------------------------------------------------------------------------

_VENDOR_QUERY_TEMPLATE = """\
You are an AP (Accounts Payable) officer at a professional organisation.
Draft a concise, professional email to a vendor querying an invoice discrepancy.

Exception type: {exception_type}
Invoice ID: {invoice_id}
Vendor name: {vendor_name}
Invoice amount: ${invoice_amount}
PO number: {po_number}
Issue: {exception_description}
Days outstanding: {days_outstanding}

Requirements:
- Professional, polite, and clear tone
- State the specific discrepancy
- Request a credit note or corrected invoice if applicable
- Include a deadline of 5 business days for response
- Sign off as "Accounts Payable Team"
- Keep under 200 words

Return ONLY the email body (no subject line, no markdown).
"""

_INTERNAL_PO_REQUEST_TEMPLATE = """\
You are an AP (Accounts Payable) officer. Draft an internal message to the
budget owner/requestor asking them to raise a Purchase Order urgently.

Invoice ID: {invoice_id}
Vendor: {vendor_name}
Invoice amount: ${invoice_amount}
Days outstanding: {days_outstanding}
Assigned approver: {approver_assigned}
Issue: {exception_description}

Requirements:
- Friendly but urgent internal tone (suitable for Slack or internal email)
- Clearly state the payment is on hold until PO is raised
- Include the invoice ID and vendor name prominently
- Mention SLA: PO must be raised within 3 business days
- Keep under 150 words

Return ONLY the message body (no subject line, no markdown).
"""

_ESCALATION_NOTE_TEMPLATE = """\
You are an AP (Accounts Payable) officer. Draft a formal escalation note
to the Finance Controller for a high-priority invoice exception.

Exception type: {exception_type}
Invoice ID: {invoice_id}
Vendor: {vendor_name}
Invoice amount: ${invoice_amount}
PO number: {po_number}
Root cause: {root_cause_hypothesis}
Recommended action: {recommended_action}
Days outstanding: {days_outstanding}
Issue: {exception_description}

Requirements:
- Formal tone appropriate for Finance Controller
- Clearly state the exception, the amount at risk, and days outstanding
- Summarise the root cause and why it requires Controller sign-off
- Request a decision within 2 business days
- Keep under 200 words

Return ONLY the escalation note body (no subject line, no markdown).
"""

_DUPLICATE_HOLD_TEMPLATE = """\
You are an AP (Accounts Payable) officer. Draft a brief internal notification
placing an invoice on hold due to a suspected duplicate.

Invoice ID: {invoice_id}
Vendor: {vendor_name}
Invoice amount: ${invoice_amount}
Days outstanding: {days_outstanding}
Issue: {exception_description}

Requirements:
- Clear and factual internal tone
- State payment is blocked pending investigation
- Explain what a duplicate means and what will happen next
- Note that AP Manager has been notified
- Keep under 120 words

Return ONLY the notification body (no subject line, no markdown).
"""

_UNAPPROVED_VENDOR_TEMPLATE = """\
You are an AP (Accounts Payable) officer. Draft an escalation message to
the Procurement team about an unapproved vendor invoice that cannot be paid.

Invoice ID: {invoice_id}
Vendor: {vendor_name}
Invoice amount: ${invoice_amount}
Days outstanding: {days_outstanding}
Issue: {exception_description}
Approver: {approver_assigned}

Requirements:
- Professional tone for Procurement team
- Clearly state the vendor is not in the approved vendor master
- Request Procurement to either onboard the vendor or confirm the correct entity
- Explain that payment is blocked until resolved
- Keep under 180 words

Return ONLY the message body (no subject line, no markdown).
"""

_TEMPLATE_MAP = {
    "vendor_query": _VENDOR_QUERY_TEMPLATE,
    "internal_po_request": _INTERNAL_PO_REQUEST_TEMPLATE,
    "escalation_note": _ESCALATION_NOTE_TEMPLATE,
    "duplicate_hold": _DUPLICATE_HOLD_TEMPLATE,
    "unapproved_vendor": _UNAPPROVED_VENDOR_TEMPLATE,
}

# ---------------------------------------------------------------------------
# LLM Client (same lazy-init pattern as rule_discoverer.py)
# ---------------------------------------------------------------------------


class _LLMClient:
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
        return cls._model

    @classmethod
    def generate(cls, prompt: str) -> tuple[str, float]:
        model = cls.get_model()
        start = time.time()
        response = model.generate_content(prompt)
        latency_ms = (time.time() - start) * 1000
        delay = get_llm_call_delay()
        if delay > 0:
            time.sleep(delay)
        return response.text.strip(), latency_ms


# ---------------------------------------------------------------------------
# Communication Drafter
# ---------------------------------------------------------------------------


class CommunicationDrafter:
    """
    Drafts communications for AP exceptions using Gemini Pro.

    Each exception that requires communication gets a draft produced from
    one of the 5 type-specific prompt templates.
    """

    def draft_one(
        self,
        exception: dict,
        classification: dict,
        resolution: dict,
    ) -> dict:
        """
        Draft a communication for a single exception.

        Args:
            exception: Original exception dict from queue.
            classification: Classification result dict.
            resolution: Resolution result dict.

        Returns:
            dict with 'communication_type', 'draft', 'success', 'error'.
        """
        comm_type = resolution.get("communication_type", "")
        invoice_id = exception.get("invoice_id", "UNKNOWN")

        if not comm_type or not resolution.get("communication_required", False):
            return {
                "communication_type": "",
                "draft": "",
                "success": True,
                "error": "",
                "note": "No communication required for this resolution path.",
            }

        template = _TEMPLATE_MAP.get(comm_type)
        if template is None:
            return {
                "communication_type": comm_type,
                "draft": "",
                "success": False,
                "error": f"Unknown communication type: {comm_type}",
            }

        # Build prompt — safely handle missing keys
        try:
            prompt = template.format(
                invoice_id=invoice_id,
                vendor_name=exception.get("vendor_name", "Unknown Vendor"),
                invoice_amount=exception.get("invoice_amount", "0"),
                po_number=exception.get("po_number", "N/A"),
                exception_type=classification.get("primary_type", "Unknown"),
                exception_description=exception.get(
                    "exception_description", ""
                ),
                days_outstanding=exception.get("days_outstanding", "0"),
                approver_assigned=exception.get(
                    "approver_assigned", "Unknown Approver"
                ),
                root_cause_hypothesis=classification.get(
                    "root_cause_hypothesis", ""
                ),
                recommended_action=classification.get(
                    "recommended_action", ""
                ),
            )
        except KeyError as e:
            return {
                "communication_type": comm_type,
                "draft": "",
                "success": False,
                "error": f"Template formatting error: {e}",
            }

        try:
            draft_text, latency_ms = _LLMClient.generate(prompt)
            logger.info(
                f"  [{invoice_id}] Drafted {comm_type} "
                f"({latency_ms:.0f}ms, {len(draft_text)} chars)"
            )
            return {
                "communication_type": comm_type,
                "draft": draft_text,
                "success": True,
                "error": "",
                "latency_ms": latency_ms,
            }
        except Exception as e:
            logger.warning(
                f"  [{invoice_id}] Communication drafting failed: {e}"
            )
            return {
                "communication_type": comm_type,
                "draft": "",
                "success": False,
                "error": str(e),
            }

    def draft_batch(
        self,
        exceptions: list[dict],
        classifications: list[dict],
        resolutions: list[dict],
    ) -> list[dict]:
        """
        Draft communications for all exceptions that require them.

        Skips exceptions where communication_required is False.

        Args:
            exceptions: Original exception dicts.
            classifications: Classification result dicts.
            resolutions: Resolution result dicts.

        Returns:
            List of communication draft dicts (one per exception).
        """
        results = []
        total_requiring_comms = sum(
            1 for r in resolutions if r.get("communication_required", False)
        )
        logger.info(
            f"Drafting communications for "
            f"{total_requiring_comms}/{len(exceptions)} exceptions..."
        )
        results = []
        exception_map = {exc.get("invoice_id"): exc for exc in exceptions}
        for cls, res in zip(classifications, resolutions):
            exc = exception_map.get(cls.get("invoice_id"), {})
            results.append(self.draft_one(exc, cls, res))

        success_count = sum(
            1
            for r in results
            if r.get("success") and r.get("draft")
        )
        logger.info(
            f"Communication drafting complete: "
            f"{success_count}/{total_requiring_comms} drafted successfully"
        )
        return results
