"""Status-aware SLA + metrics: resolving a case takes it off the clock.

Locks in the cross-screen propagation fix — once an invoice is RESOLVED in the
Resolution Tracker it must drop out of the live at-risk / open counts that the
dashboard and assistant read (while the operator digest keeps the raw breach
count, tested separately in test_digest.py)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal


def _row(inv, vendor="Acme", amount="1000"):
    from app.schemas import ExceptionRow

    return ExceptionRow(
        invoice_id=inv, vendor_name=vendor, invoice_amount=Decimal(amount),
        po_number="PO", exception_type="Price Variance", exception_description="d",
        days_outstanding=0,
    )


def _res(inv, sla_hours=8):
    from app.schemas import ResolutionDecision, ResolutionPath

    return ResolutionDecision(
        invoice_id=inv, resolution_path=ResolutionPath.ESCALATE_CONTROLLER,
        rule_id="r", rule_version="v1", rule_trace=["t"],
        requires_communication=True, sla_hours=sla_hours,
    )


def _state(cases):
    from app.graph.builder import initial_state

    state = initial_state("run_sa", "default")
    state["status"] = "AWAITING_REVIEW"
    state["created_at"] = datetime.now(UTC) - timedelta(hours=10)  # both breach 8h SLA
    state["rows"] = [_row("INV-1"), _row("INV-2")]
    state["resolutions"] = [_res("INV-1"), _res("INV-2")]
    state["cases"] = cases
    return state


def test_evaluate_sla_exclude_closed_drops_resolved():
    from app.comms.sla import evaluate_sla

    state = _state({"INV-1": {"status": "RESOLVED"}, "INV-2": {"status": "OPEN"}})
    now = datetime.now(UTC)

    raw = evaluate_sla(state, now=now)
    assert raw["breached"] == 2  # raw view counts both, regardless of case status

    actionable = evaluate_sla(state, now=now, exclude_closed=True)
    assert actionable["breached"] == 1  # the resolved one is off the clock
    assert [i["invoice_id"] for i in actionable["breached_items"]] == ["INV-2"]


def test_metrics_endpoint_overlay_is_status_aware(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("RUN_STORE_BACKEND", "memory")
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_KEY", "")
    monkeypatch.setenv("DB_PERSISTENCE_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.api import store as store_mod
    store_mod.reset_store_cache()
    store = store_mod.get_store()

    from app.schemas.metrics import DashboardMetrics

    state = _state({"INV-1": {"status": "RESOLVED"}, "INV-2": {"status": "OPEN"}})
    state["metrics"] = DashboardMetrics(
        total_exceptions=2, auto_resolvable_count=0, escalations_required=2,
        total_exception_value=Decimal("2000"), breakdown_by_type={}, breakdown_by_severity={},
        breakdown_by_resolution_path={}, top_5_actionable=[], sla_at_risk_count=2,
        average_confidence=0.9,
    )
    store.put(state)

    from fastapi.testclient import TestClient
    from app.api.main import app

    r = TestClient(app).get("/v1/runs/run_sa/metrics")
    assert r.status_code == 200, r.text
    m = r.json()["metrics"]
    assert m["resolved_count"] == 1
    assert m["open_count"] == 1
    assert m["sla_at_risk_count"] == 1  # the resolved invoice no longer counts

    store_mod.reset_store_cache()
    get_settings.cache_clear()
