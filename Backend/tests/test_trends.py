"""Cross-run trend analytics (GET /v1/analytics/trends).

Per-run aggregates (oldest first) + overall totals, including time-to-resolve
derived from the case lifecycle.
"""
from __future__ import annotations

from decimal import Decimal


def _bootstrap_memory_store(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("RUN_STORE_BACKEND", "memory")
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_KEY", "")
    monkeypatch.setenv("DB_PERSISTENCE_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.api import store as store_mod
    store_mod.reset_store_cache()
    return store_mod.get_store()


def _metrics(total, auto, esc, val, high, conf, sla):
    from app.schemas.metrics import DashboardMetrics

    return DashboardMetrics(
        total_exceptions=total,
        auto_resolvable_count=auto,
        escalations_required=esc,
        total_exception_value=Decimal(val),
        breakdown_by_type={},
        breakdown_by_severity={"HIGH": high},
        breakdown_by_resolution_path={},
        top_5_actionable=[],
        sla_at_risk_count=sla,
        average_confidence=conf,
    )


def _case(inv, status, updated_at):
    return {
        "invoice_id": inv,
        "status": status,
        "note": None,
        "updated_at": updated_at,
        "updated_by": "u",
    }


def test_trends_aggregates_and_cycle_time(monkeypatch):
    store = _bootstrap_memory_store(monkeypatch)
    from app.graph.builder import initial_state

    a = initial_state("run_a", "default")
    a["created_at"] = "2026-06-01T00:00:00Z"
    a["metrics"] = _metrics(10, 6, 2, "1000", 1, 0.9, 1)
    # INV-1 resolved 5h after the run started.
    a["cases"] = {"INV-1": _case("INV-1", "RESOLVED", "2026-06-01T05:00:00Z")}
    store.put(a)

    b = initial_state("run_b", "default")
    b["created_at"] = "2026-06-10T00:00:00Z"
    b["metrics"] = _metrics(20, 10, 5, "2000", 3, 0.95, 2)
    b["cases"] = {}
    store.put(b)

    # An in-progress run with no metrics is skipped.
    c = initial_state("run_c", "default")
    c["created_at"] = "2026-06-15T00:00:00Z"
    store.put(c)

    from fastapi.testclient import TestClient
    from app.api.main import app

    body = TestClient(app).get("/v1/analytics/trends").json()

    # Only the two runs with metrics, oldest first.
    assert [r["run_id"] for r in body["runs"]] == ["run_a", "run_b"]

    run_a = body["runs"][0]
    assert run_a["total_exceptions"] == 10
    assert run_a["resolved"] == 1
    assert run_a["avg_cycle_hours"] == 5.0  # 5 hours to resolve

    run_b = body["runs"][1]
    assert run_b["resolved"] == 0
    assert run_b["avg_cycle_hours"] is None

    t = body["totals"]
    assert t["runs"] == 2
    assert t["total_exceptions"] == 30
    assert t["total_value"] == "3000"
    assert t["resolved"] == 1
    assert t["avg_cycle_hours"] == 5.0


def test_trends_empty(monkeypatch):
    _bootstrap_memory_store(monkeypatch)
    from fastapi.testclient import TestClient
    from app.api.main import app

    body = TestClient(app).get("/v1/analytics/trends").json()
    assert body["runs"] == []
    assert body["totals"]["runs"] == 0
    assert body["totals"]["avg_cycle_hours"] is None
