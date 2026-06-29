"""Reviewer digest enrichment — POST /v1/runs/{id}/notify now folds in the case
lifecycle (in progress / resolved / needs follow-up) on top of the SLA counts."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal


def _row(invoice_id):
    from app.schemas import ExceptionRow

    return ExceptionRow(
        invoice_id=invoice_id, vendor_name="Acme", invoice_amount=Decimal("1000"),
        po_number="PO-1", exception_type="Price Variance",
        exception_description="x", days_outstanding=10,
    )


def _res(invoice_id, sla_hours):
    from app.schemas import ResolutionDecision, ResolutionPath

    return ResolutionDecision(
        invoice_id=invoice_id, resolution_path=ResolutionPath.ESCALATE_CONTROLLER,
        rule_id="r", rule_version="v1", rule_trace=["t"],
        requires_communication=True, sla_hours=sla_hours,
    )


def _case(inv, status):
    return {"invoice_id": inv, "status": status, "note": None, "updated_at": None, "updated_by": "u"}


def test_digest_folds_in_case_lifecycle(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("RUN_STORE_BACKEND", "memory")
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_KEY", "")
    monkeypatch.setenv("DB_PERSISTENCE_ENABLED", "false")
    monkeypatch.setenv("COMMS_DRYRUN", "true")
    monkeypatch.setenv("COMMS_AP_TEAM_MAILBOX", "ops@example.com")
    monkeypatch.setenv("COMMS_SENT_DIR", str(tmp_path / "sent"))
    from app.config import get_settings
    get_settings.cache_clear()
    from app.api import store as store_mod
    store_mod.reset_store_cache()
    store = store_mod.get_store()

    from app.graph.builder import initial_state

    state = initial_state("run_dig", "default")
    state["status"] = "AWAITING_REVIEW"
    state["created_at"] = datetime.now(UTC) - timedelta(hours=10)
    state["rows"] = [_row("INV-1"), _row("INV-2")]
    # Both breach an 8h SLA (run started 10h ago).
    state["resolutions"] = [_res("INV-1", 8), _res("INV-2", 8)]
    # INV-1 already resolved → not a follow-up; INV-2 open → needs follow-up.
    state["cases"] = {"INV-1": _case("INV-1", "RESOLVED"), "INV-2": _case("INV-2", "OPEN")}
    store.put(state)

    from fastapi.testclient import TestClient
    from app.api.main import app

    r = TestClient(app).post("/v1/runs/run_dig/notify")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["notification"]["status"] == "dryrun"

    s = body["summary"]
    assert s["breached"] == 2
    assert s["resolved"] == 1
    assert s["in_progress"] == 0
    assert s["needs_follow_up"] == 1  # INV-2: breached AND still open

    store_mod.reset_store_cache()
    get_settings.cache_clear()
