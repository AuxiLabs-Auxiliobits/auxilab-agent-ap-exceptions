"""'Ask the desk' — read-only grounded Q&A over a run (POST /v1/runs/{id}/ask).

Deterministic and grounded: answers are computed from the run state, so the
assistant cites real invoice ids and never invents figures.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace


def _vendors_ctx(vendor_by_invoice: dict[str, str]):
    from app.api.assistant import _Ctx

    rows = {
        inv: SimpleNamespace(vendor_name=v, invoice_amount=100)
        for inv, v in vendor_by_invoice.items()
    }
    return _Ctx(rows=rows, cls={}, res={}, cases={}, metrics=None, sla={})


def test_answer_vendors_lists_only_repeat_offenders():
    """A vendor with >1 exception is surfaced (most first); single-exception
    vendors are not listed, and their invoices are cited."""
    from app.api.assistant import _answer_vendors

    out = _answer_vendors(
        _vendors_ctx({"INV-1": "Acme", "INV-2": "Acme", "INV-3": "Globex"})
    )
    assert out["intent"] == "vendors"
    assert "2 vendor(s) across 3 exception(s)" in out["answer"]
    assert "Acme — 2 exception(s)" in out["answer"]
    assert "Globex" not in out["answer"]  # only 1 exception → not a repeat offender
    assert set(out["cited_invoice_ids"]) == {"INV-1", "INV-2"}


def test_answer_vendors_when_none_have_multiple():
    from app.api.assistant import _answer_vendors

    out = _answer_vendors(_vendors_ctx({"INV-1": "Acme", "INV-2": "Globex"}))
    assert "2 vendor(s) across 2 exception(s)" in out["answer"]
    assert "no vendor has more than one exception" in out["answer"].lower()
    assert out["cited_invoice_ids"] == []


def _bootstrap_memory_store(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("RUN_STORE_BACKEND", "memory")
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_KEY", "")
    monkeypatch.setenv("DB_PERSISTENCE_ENABLED", "false")
    # This suite asserts exact deterministic answers, so pin the assistant to its
    # LLM-free path — clear any AI provider keys present in the environment.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.api import store as store_mod
    store_mod.reset_store_cache()
    return store_mod.get_store()


def _row(inv, vendor, amount, etype, days):
    from app.schemas import ExceptionRow

    return ExceptionRow(
        invoice_id=inv, vendor_name=vendor, invoice_amount=Decimal(amount),
        po_number="PO", exception_type=etype, exception_description="d", days_outstanding=days,
    )


def _cls(inv, etype, sev, conf):
    from app.schemas import ClassificationResult

    return ClassificationResult(
        invoice_id=inv, primary_exception_type=etype, root_cause="unit price over PO",
        severity_ai_suggested=sev, severity=sev, confidence_score=conf,
        rationale="r", model_id="mock", prompt_version="v1",
    )


def _res(inv, path, sla):
    from app.schemas import ResolutionDecision

    return ResolutionDecision(
        invoice_id=inv, resolution_path=path, rule_id="rule_x", rule_version="v1",
        rule_trace=["t"], requires_communication=True, sla_hours=sla,
    )


def _seed(store):
    from app.graph.builder import initial_state
    from app.schemas import PrimaryExceptionType, ResolutionPath, Severity

    state = initial_state("run_ask", "default")
    state["status"] = "AWAITING_REVIEW"
    state["created_at"] = datetime.now(UTC)
    state["rows"] = [
        _row("INV-1", "Acme", "30000", "Price Variance", 40),  # old → breaches its 8h SLA
        _row("INV-2", "Globex", "2000", "Missing PO", 0),       # fresh → on track
    ]
    state["classifications"] = [
        _cls("INV-1", PrimaryExceptionType.PRICE_VARIANCE, Severity.HIGH, 0.9),
        _cls("INV-2", PrimaryExceptionType.MISSING_PO, Severity.LOW, 0.8),
    ]
    state["resolutions"] = [
        _res("INV-1", ResolutionPath.ESCALATE_CONTROLLER, 8),
        _res("INV-2", ResolutionPath.REQUEST_PO, 48),
    ]
    state["cases"] = {}
    store.put(state)


def test_ask_desk_is_grounded(monkeypatch):
    store = _bootstrap_memory_store(monkeypatch)
    _seed(store)

    from fastapi.testclient import TestClient
    from app.api.main import app

    c = TestClient(app)

    def ask(q):
        r = c.post("/v1/runs/run_ask/ask", json={"question": q})
        assert r.status_code == 200, r.text
        return r.json()

    # Specific invoice → explains it, cites it.
    a = ask("why did INV-1 escalate?")
    assert a["intent"] == "invoice"
    assert a["cited_invoice_ids"] == ["INV-1"]
    assert "Escalate to Controller" in a["answer"]  # friendly label, not the raw code

    # A bare invoice number (not the full id) still resolves — and answers the
    # amount, instead of falling through to the run summary.
    a = ask("what is the total amount of invoice 2?")
    assert a["intent"] == "invoice"
    assert a["cited_invoice_ids"] == ["INV-2"]
    assert "$2,000" in a["answer"]

    # SLA / at risk → cites the breached item.
    a = ask("what is at risk?")
    assert a["intent"] == "sla"
    assert "INV-1" in a["cited_invoice_ids"]
    assert "INV-2" not in a["cited_invoice_ids"]  # fresh, on track

    # Needs follow-up → the breached, still-open item.
    a = ask("what needs follow-up today?")
    assert a["intent"] == "follow_up"
    assert "INV-1" in a["cited_invoice_ids"]

    # Vendors → leads with the total vendor count and answers the ">1" question.
    a = ask("which vendors have the most exceptions?")
    assert a["intent"] == "vendors"
    assert "2 vendor(s) across 2 exception(s)" in a["answer"]  # total reported
    assert "no vendor has more than one exception" in a["answer"].lower()
    assert "Acme" in a["answer"]

    # Summary only when explicitly asked.
    a = ask("give me a summary")
    assert a["intent"] == "summary"
    assert "2 exception" in a["answer"]

    # Off-topic question → polite refusal, NOT the run summary.
    a = ask("weather today")
    assert a["intent"] == "out_of_scope"
    assert "2 exception" not in a["answer"]
    assert "only answer" in a["answer"].lower()

    # Empty question → 400.
    assert c.post("/v1/runs/run_ask/ask", json={"question": "  "}).status_code == 400
