"""Hybrid 'Ask the desk' — LLM understanding + RAG over the deterministic core.

Covers:
  - BM25 retrieval ranks the right invoice and returns nothing for off-topic queries.
  - With no LLM (mock mode) the hybrid path equals the deterministic engine.
  - With an LLM, paraphrases route to the right deterministic intent (numbers
    still computed from run state) and free-text questions go through RAG with
    grounded, citation-filtered answers.
  - An LLM failure degrades gracefully to keyword routing.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal


# --------------------------------------------------------------------------- #
# Seed helpers                                                                 #
# --------------------------------------------------------------------------- #
def _row(inv, vendor, amount, etype, days, desc):
    from app.schemas import ExceptionRow

    return ExceptionRow(
        invoice_id=inv, vendor_name=vendor, invoice_amount=Decimal(amount),
        po_number="PO", exception_type=etype, exception_description=desc,
        days_outstanding=days,
    )


def _cls(inv, etype, sev, root_cause):
    from app.schemas import ClassificationResult

    return ClassificationResult(
        invoice_id=inv, primary_exception_type=etype, root_cause=root_cause,
        severity_ai_suggested=sev, severity=sev, confidence_score=0.9,
        rationale="r", model_id="mock", prompt_version="v1",
    )


def _res(inv, path, sla):
    from app.schemas import ResolutionDecision

    return ResolutionDecision(
        invoice_id=inv, resolution_path=path, rule_id="rule_x", rule_version="v1",
        rule_trace=["t"], requires_communication=True, sla_hours=sla,
    )


def _state():
    from app.graph.builder import initial_state
    from app.schemas import PrimaryExceptionType, ResolutionPath, Severity

    state = initial_state("run_hy", "default")
    state["status"] = "AWAITING_REVIEW"
    state["created_at"] = datetime.now(UTC)
    state["rows"] = [
        _row("INV-1", "Acme", "30000", "Price Variance", 40, "unit price billed above PO"),
        _row("INV-2", "Globex", "2000", "Missing PO", 0, "no purchase order on the invoice"),
        _row("INV-3", "Initech", "8000", "Quantity Mismatch", 5, "short shipment received"),
    ]
    state["classifications"] = [
        _cls("INV-1", PrimaryExceptionType.PRICE_VARIANCE, Severity.HIGH,
             "unit price exceeds the agreed contract pricing schedule"),
        _cls("INV-2", PrimaryExceptionType.MISSING_PO, Severity.LOW,
             "purchase order number is missing from the supplier invoice"),
        _cls("INV-3", PrimaryExceptionType.QUANTITY_MISMATCH, Severity.MEDIUM,
             "received quantity does not match the goods receipt note"),
    ]
    state["resolutions"] = [
        _res("INV-1", ResolutionPath.ESCALATE_CONTROLLER, 8),   # old → breaches
        _res("INV-2", ResolutionPath.REQUEST_PO, 48),
        _res("INV-3", ResolutionPath.REQUEST_PO, 48),
    ]
    state["cases"] = {}
    return state


class _FakeClient:
    """Stands in for ClaudeClient: returns a canned plan, then a canned answer."""

    is_mock = False

    def __init__(self, plan: dict, answer: dict | None = None):
        self._plan = plan
        self._answer = answer or {}
        self.calls: list[tuple[str, str]] = []

    async def tool_call(self, *, purpose, system, user_text, tool, max_tokens, temperature):
        from app.ai.client import ToolCallResult

        self.calls.append((tool["name"], user_text))
        payload = self._plan if tool["name"] == "emit_query_plan" else self._answer
        return ToolCallResult(
            name=tool["name"], input=dict(payload), model_id="fake",
            stop_reason="tool_use", usage={}, provider="fake",
        )


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# Retrieval                                                                    #
# --------------------------------------------------------------------------- #
def test_bm25_ranks_relevant_invoice():
    from app.ai.retrieval import retrieve

    state = _state()
    assert retrieve(state, "contract pricing dispute", top_k=3)[0] == "INV-1"
    assert retrieve(state, "missing purchase order number", top_k=3)[0] == "INV-2"
    assert retrieve(state, "goods receipt quantity", top_k=3)[0] == "INV-3"
    # Off-topic query shares no terms → no results (never an arbitrary "best").
    assert retrieve(state, "weather forecast tomorrow") == []


# --------------------------------------------------------------------------- #
# Mock fallback parity                                                         #
# --------------------------------------------------------------------------- #
def test_mock_mode_equals_deterministic(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "AZURE_OPENAI_API_KEY"):
        monkeypatch.setenv(k, "")
    from app.config import get_settings
    get_settings.cache_clear()

    from app.ai.client import ClaudeClient
    from app.api.assistant import answer_question
    from app.api.assistant_hybrid import answer_question_hybrid

    client = ClaudeClient()
    assert client.is_mock  # no keys → mock provider

    state = _state()
    now = datetime.now(UTC)
    for q in ("what is at risk?", "give me a summary", "why did INV-1 escalate?", "weather"):
        h = _run(answer_question_hybrid(state, q, now=now, client=client))
        assert h == answer_question(state, q, now=now)


# --------------------------------------------------------------------------- #
# LLM-routed paths                                                             #
# --------------------------------------------------------------------------- #
def test_paraphrase_routes_to_deterministic_intent():
    """A phrasing the keyword engine would refuse now routes correctly, and the
    answer's numbers still come from run state, not the model."""
    from app.api.assistant_hybrid import answer_question_hybrid

    state = _state()
    fake = _FakeClient({"intent": "sla", "invoice_ids": []})
    res = _run(answer_question_hybrid(
        state, "anything I should worry about?", now=datetime.now(UTC), client=fake
    ))
    assert res["intent"] == "sla"
    assert "INV-1" in res["cited_invoice_ids"]      # the breached item, computed deterministically
    assert "INV-2" not in res["cited_invoice_ids"]  # fresh, on track
    assert [c[0] for c in fake.calls] == ["emit_query_plan"]  # no answer call needed


def test_invoice_intent_with_extracted_entity():
    from app.api.assistant_hybrid import answer_question_hybrid

    state = _state()
    fake = _FakeClient({"intent": "invoice", "invoice_ids": ["2"]})
    res = _run(answer_question_hybrid(state, "tell me about the Globex one", now=datetime.now(UTC), client=fake))
    assert res["intent"] == "invoice"
    assert res["cited_invoice_ids"] == ["INV-2"]


def test_search_path_is_grounded_and_filters_citations():
    from app.api.assistant_hybrid import answer_question_hybrid

    state = _state()
    fake = _FakeClient(
        {"intent": "search", "search_terms": "contract pricing dispute", "invoice_ids": []},
        {"answer": "INV-1 is billed above the agreed contract pricing.",
         "cited_invoice_ids": ["INV-1", "INV-999"]},  # INV-999 was never retrieved
    )
    res = _run(answer_question_hybrid(state, "are there any pricing disputes?", now=datetime.now(UTC), client=fake))
    assert res["intent"] == "search"
    assert "contract pricing" in res["answer"].lower()
    assert res["cited_invoice_ids"] == ["INV-1"]  # invented id filtered out
    # Two LLM calls: plan then grounded answer; the grounding block carried real facts.
    assert [c[0] for c in fake.calls] == ["emit_query_plan", "emit_grounded_answer"]
    grounded_prompt = fake.calls[1][1]
    assert "INV-1" in grounded_prompt and "Acme" in grounded_prompt


def test_search_with_no_matches_does_not_call_model_for_answer():
    from app.api.assistant_hybrid import answer_question_hybrid

    state = _state()
    fake = _FakeClient({"intent": "search", "search_terms": "quantum cryptography blockchain"})
    res = _run(answer_question_hybrid(state, "any blockchain invoices?", now=datetime.now(UTC), client=fake))
    assert res["intent"] == "search"
    assert res["cited_invoice_ids"] == []
    assert "couldn't find" in res["answer"].lower()
    assert [c[0] for c in fake.calls] == ["emit_query_plan"]  # retrieval empty → no grounded call


def test_out_of_scope_plan_gets_keyword_second_chance():
    """If the planner misclassifies an answerable question as out_of_scope, the
    deterministic keyword cascade still answers it (no false refusal)."""
    from app.api.assistant_hybrid import answer_question_hybrid

    state = _state()
    fake = _FakeClient({"intent": "out_of_scope"})
    res = _run(answer_question_hybrid(state, "what is at risk?", now=datetime.now(UTC), client=fake))
    assert res["intent"] == "sla"  # rescued by the keyword cascade
    assert "INV-1" in res["cited_invoice_ids"]


def test_truly_off_topic_plan_still_refuses():
    from app.api.assistant_hybrid import answer_question_hybrid

    state = _state()
    fake = _FakeClient({"intent": "out_of_scope"})
    res = _run(answer_question_hybrid(state, "what's the weather tomorrow?", now=datetime.now(UTC), client=fake))
    assert res["intent"] == "out_of_scope"  # keyword cascade also finds nothing → refuse


def test_llm_failure_falls_back_to_keyword_engine():
    from app.api.assistant_hybrid import answer_question_hybrid

    class _Boom:
        is_mock = False

        async def tool_call(self, **_):
            raise RuntimeError("provider down")

    state = _state()
    res = _run(answer_question_hybrid(state, "what is at risk?", now=datetime.now(UTC), client=_Boom()))
    assert res["intent"] == "sla"  # graceful fallback to deterministic routing
    assert "INV-1" in res["cited_invoice_ids"]
