"""Tool-use JSON schemas passed to Claude.

These mirror the corresponding Pydantic models but are kept hand-authored
because Anthropic's tool-use API requires a tight JSON Schema with no
extras Claude doesn't understand (no `$defs`, no `discriminator`, etc.).
"""
from __future__ import annotations

CLASSIFY_TOOL = {
    "name": "emit_classification",
    "description": (
        "Emit the classification result for one AP exception. "
        "Always use this tool. Never reply in free text."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "invoice_id": {"type": "string"},
            "primary_exception_type": {
                "type": "string",
                "enum": [
                    "Price Variance",
                    "Quantity Mismatch",
                    "Missing PO",
                    "Duplicate",
                    "Unapproved Vendor",
                    "GRN Not Received",
                    "Other",
                ],
            },
            "root_cause": {"type": "string", "maxLength": 280},
            "severity": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
            "confidence_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "rationale": {"type": "string", "maxLength": 500},
        },
        "required": [
            "invoice_id",
            "primary_exception_type",
            "root_cause",
            "severity",
            "confidence_score",
            "rationale",
        ],
        "additionalProperties": False,
    },
}


DRAFT_TOOL = {
    "name": "emit_draft",
    "description": "Emit the drafted communication for one AP exception.",
    "input_schema": {
        "type": "object",
        "properties": {
            "subject": {"type": "string", "maxLength": 200},
            "body": {"type": "string", "minLength": 1, "maxLength": 4000},
        },
        "required": ["body"],
        "additionalProperties": False,
    },
}


# ---- "Ask the desk" hybrid assistant -------------------------------------- #
# The assistant understands a free-form question with the LLM (this tool),
# computes all numbers deterministically from run state, and only uses the
# model to phrase grounded answers (GROUNDED_ANSWER_TOOL). Forcing tool use
# means the model returns a structured plan, never free text.

QUERY_PLAN_TOOL = {
    "name": "emit_query_plan",
    "description": (
        "Classify the user's question about an accounts-payable (AP) exception "
        "run and extract any entities it names. Always use this tool; never "
        "reply in free text.\n\n"
        "Pick the single best intent:\n"
        "- invoice: asks about ONE specific invoice (by id or number). Prefer "
        "this whenever the question names a specific invoice, even if it also "
        "mentions escalation, SLA, severity, or a vendor.\n"
        "- follow_up: which items need chasing / are overdue / stuck.\n"
        "- sla: what is at risk / due / breaching its SLA deadline.\n"
        "- escalations: what was escalated to a controller.\n"
        "- severity: high-severity / urgent / serious exceptions.\n"
        "- vendors: which vendors / suppliers have the most exceptions.\n"
        "- duplicates: duplicate / double-billed invoices.\n"
        "- summary: an overview / status / counts of the whole run.\n"
        "- search: any other on-topic question that needs looking across the "
        "invoices' notes/reasons/descriptions (e.g. 'which invoices mention a "
        "pricing dispute', 'anything about contract terms'). Put the salient "
        "keywords in search_terms.\n"
        "- out_of_scope: anything not about this AP exception run.\n\n"
        "Extract invoice_ids (full ids like 'INV-2001' or bare numbers), a "
        "vendor name if one is named, and search_terms (the content words to "
        "search for) when intent is search."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": [
                    "invoice",
                    "follow_up",
                    "sla",
                    "escalations",
                    "severity",
                    "vendors",
                    "duplicates",
                    "summary",
                    "search",
                    "out_of_scope",
                ],
            },
            "invoice_ids": {"type": "array", "items": {"type": "string"}},
            "vendor": {"type": "string"},
            "search_terms": {"type": "string"},
        },
        "required": ["intent"],
        "additionalProperties": False,
    },
}


GROUNDED_ANSWER_TOOL = {
    "name": "emit_grounded_answer",
    "description": (
        "Answer the user's question using ONLY the invoice context provided in "
        "the message. Never invent invoice ids, amounts, vendors, dates, or any "
        "figure that is not present in that context — if the context doesn't "
        "contain the answer, say so plainly. Cite the invoice ids you actually "
        "used in cited_invoice_ids. Always use this tool; never reply in free "
        "text."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "answer": {"type": "string", "minLength": 1, "maxLength": 1200},
            "cited_invoice_ids": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["answer", "cited_invoice_ids"],
        "additionalProperties": False,
    },
}
