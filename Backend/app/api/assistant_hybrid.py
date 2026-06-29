"""Hybrid 'Ask the desk' — LLM understanding + RAG on top of the deterministic core.

Pipeline for one question:

  1. PLAN (NLP): the LLM reads the question and emits a structured query plan
     (intent + entities) via forced tool use — robust to paraphrase, synonyms,
     and typos, unlike keyword matching. (app/ai/schemas.QUERY_PLAN_TOOL)
  2. ROUTE:
       - a deterministic intent (sla, summary, a specific invoice, …) →
         answered by the deterministic core (app/api/assistant.py), so every
         number stays exact and auditable.
       - "search" (free-form question over invoice notes) → RAG: BM25 retrieves
         the most relevant invoices (app/ai/retrieval.py), their real facts are
         handed to the LLM, and the model answers GROUNDED in that context,
         citing invoice ids and never inventing figures.

Graceful degradation: with no LLM configured (mock mode) — or if any LLM call
fails — the whole thing falls back to the deterministic keyword engine, so the
endpoint never breaks and tests stay deterministic.
"""
from __future__ import annotations

import logging
from datetime import datetime

from app.ai.client import ClaudeClient
from app.ai.retrieval import retrieve
from app.ai.schemas import GROUNDED_ANSWER_TOOL, QUERY_PLAN_TOOL
from app.api import assistant

log = logging.getLogger("ap_agent.assistant_hybrid")

_PLANNER_SYSTEM = (
    "You route questions for an accounts-payable (AP) exception review desk. "
    "You do not answer the question or state any figures — you only classify "
    "the user's intent and extract the entities they mention, using the "
    "emit_query_plan tool. Be liberal in mapping paraphrases, synonyms, and "
    "typos to the right intent. If the question is not about this AP exception "
    "run, use intent out_of_scope."
)

_ANSWER_SYSTEM = (
    "You are a grounded assistant for an accounts-payable exception review desk. "
    "Answer the user's question using ONLY the invoice context block provided in "
    "the user message. Rules: never state an invoice id, amount, vendor, date, "
    "count, or any figure that is not present in the context; if the context "
    "doesn't contain the answer, say so plainly rather than guessing; keep the "
    "answer concise; cite the invoice ids you used. Always answer with the "
    "emit_grounded_answer tool."
)

_MAX_RETRIEVED = 6


def _plan_from(result_input: dict) -> dict:
    intent = (result_input.get("intent") or "out_of_scope").strip()
    if intent not in assistant.DETERMINISTIC_INTENTS and intent != "search":
        intent = "out_of_scope"
    ids = result_input.get("invoice_ids") or []
    if not isinstance(ids, list):
        ids = [ids]
    return {
        "intent": intent,
        "invoice_ids": [str(i) for i in ids],
        "vendor": (result_input.get("vendor") or None),
        "search_terms": (result_input.get("search_terms") or None),
    }


def _grounding_block(state: dict, invoice_ids: list[str], *, now: datetime) -> str:
    """Render real, run-state facts for the retrieved invoices as the LLM's
    sole source of truth. Every value here comes straight from the run."""
    ctx = assistant._build_ctx(state, now=now)
    lines: list[str] = []
    for inv in invoice_ids:
        row = ctx.rows.get(inv)
        if row is None:
            continue
        c = ctx.cls.get(inv)
        r = ctx.res.get(inv)
        fields = [
            f"invoice_id: {inv}",
            f"vendor: {getattr(row, 'vendor_name', 'unknown')}",
            f"amount: {assistant._money(getattr(row, 'invoice_amount', None))}",
            f"days_outstanding: {getattr(row, 'days_outstanding', 'n/a')}",
        ]
        if getattr(row, "exception_description", None):
            fields.append(f"description: {row.exception_description}")
        if c is not None:
            fields.append(f"exception_type: {c.primary_exception_type.value}")
            fields.append(f"severity: {c.severity.value}")
            if getattr(c, "root_cause", None):
                fields.append(f"root_cause: {c.root_cause}")
            if getattr(c, "rationale", None):
                fields.append(f"rationale: {c.rationale}")
        if r is not None:
            fields.append(f"resolution_path: {r.resolution_path.value}")
            fields.append(f"sla_hours: {r.sla_hours}")
        fields.append(f"case_status: {assistant._case_status(ctx.cases, inv)}")
        lines.append("- " + "; ".join(fields))
    return "\n".join(lines)


async def _generate_grounded(
    client: ClaudeClient, state: dict, question: str, plan: dict, *, now: datetime
) -> dict:
    """RAG path: retrieve relevant invoices, answer grounded in their facts."""
    query = plan.get("search_terms") or question
    if plan.get("vendor"):
        query = f"{plan['vendor']} {query}"
    invoice_ids = retrieve(state, query, top_k=_MAX_RETRIEVED)
    if not invoice_ids:
        return {
            "answer": (
                "I couldn't find any invoice in this run whose notes match that. "
                "Try rephrasing, or ask for a summary, SLA risk, escalations, "
                "high severity, vendors, duplicates, or a specific invoice."
            ),
            "cited_invoice_ids": [],
            "intent": "search",
        }

    block = _grounding_block(state, invoice_ids, now=now)
    user_text = (
        f"Question: {question}\n\n"
        f"Invoice context (the only facts you may use):\n{block}"
    )
    result = await client.tool_call(
        purpose="assistant",
        system=_ANSWER_SYSTEM,
        user_text=user_text,
        tool=GROUNDED_ANSWER_TOOL,
        max_tokens=700,
        temperature=0.0,
    )
    data = result.input or {}
    answer = (data.get("answer") or "").strip()
    if not answer:
        # Model returned nothing usable — surface what we retrieved deterministically.
        listing = "\n".join(f"  • {assistant._line(assistant._build_ctx(state, now=now), i)}" for i in invoice_ids)
        return {
            "answer": f"Relevant invoices for that query:\n{listing}",
            "cited_invoice_ids": invoice_ids,
            "intent": "search",
        }
    cited = data.get("cited_invoice_ids") or []
    # Only keep citations the model was actually given (no invented ids).
    cited = [i for i in (str(x) for x in cited) if i in set(invoice_ids)]
    return {"answer": answer, "cited_invoice_ids": cited, "intent": "search"}


async def answer_question_hybrid(
    state: dict,
    question: str,
    *,
    now: datetime,
    client: ClaudeClient | None = None,
) -> dict:
    """LLM-routed, RAG-grounded answer with a deterministic fallback.

    Returns ``{answer, cited_invoice_ids, intent}``. When no LLM is configured
    (mock mode) or any LLM call fails, falls back to the deterministic keyword
    engine so the endpoint always responds and never invents a figure."""
    client = client or ClaudeClient()

    # No LLM available → deterministic engine (preserves exact prior behavior).
    if client.is_mock:
        return assistant.answer_question(state, question, now=now)

    if not state.get("rows"):
        return assistant.answer_question(state, question, now=now)

    try:
        plan_result = await client.tool_call(
            purpose="assistant",
            system=_PLANNER_SYSTEM,
            user_text=question,
            tool=QUERY_PLAN_TOOL,
            max_tokens=400,
            temperature=0.0,
        )
        plan = _plan_from(plan_result.input or {})
    except Exception:  # noqa: BLE001 — never let the LLM break the desk
        log.warning("assistant: query planning failed; falling back to keyword routing", exc_info=True)
        return assistant.answer_question(state, question, now=now)

    if plan["intent"] == "search":
        try:
            return await _generate_grounded(client, state, question, plan, now=now)
        except Exception:  # noqa: BLE001
            log.warning("assistant: grounded answer failed; falling back to keyword routing", exc_info=True)
            return assistant.answer_question(state, question, now=now)

    if plan["intent"] == "out_of_scope":
        # A weaker planner model can misclassify an answerable question as
        # out-of-scope. Give the deterministic keyword cascade a second chance
        # before refusing — if it recognises the question, use that answer.
        kw = assistant.answer_question(state, question, now=now)
        if kw["intent"] != "out_of_scope":
            return kw
        return assistant.answer_for_intent(state, intent="out_of_scope", now=now)

    # Deterministic intent — numbers computed from run state, not the model.
    return assistant.answer_for_intent(
        state, intent=plan["intent"], now=now, invoice_ids=plan["invoice_ids"]
    )
