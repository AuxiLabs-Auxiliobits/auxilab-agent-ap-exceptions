"""Resolution lifecycle (cases) — GET/PATCH /v1/runs/{id}/cases/{invoice_id}.

A human can advance an exception Open → In progress → Resolved / Won't fix; each
change is validated, tenant-owned, and append-only audited (CASE_UPDATE).
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


def _row(inv: str):
    from app.schemas.exception_row import ExceptionRow

    return ExceptionRow(
        invoice_id=inv,
        vendor_name="Acme",
        invoice_amount=Decimal("100"),
        exception_type="Price Variance",
        exception_description="desc",
        days_outstanding=10,
    )


def _seed_run(store, run_id="run_cases"):
    from app.graph.builder import initial_state

    state = initial_state(run_id, "default")
    state["created_at"] = "2026-06-20T00:00:00Z"
    state["rows"] = [_row("INV-1"), _row("INV-2")]
    store.put(state)
    return run_id


def test_case_lifecycle_and_audit(monkeypatch):
    store = _bootstrap_memory_store(monkeypatch)
    run_id = _seed_run(store)

    from fastapi.testclient import TestClient
    from app.api.main import app

    client = TestClient(app)

    # Starts empty — the UI treats missing entries as OPEN.
    assert client.get(f"/v1/runs/{run_id}/cases").json()["cases"] == {}

    # Advance INV-1 to IN_PROGRESS with a note.
    r = client.patch(
        f"/v1/runs/{run_id}/cases/INV-1",
        json={"status": "IN_PROGRESS", "note": "emailed vendor for PO"},
    )
    assert r.status_code == 200, r.text
    case = r.json()["case"]
    assert case["status"] == "IN_PROGRESS"
    assert case["note"] == "emailed vendor for PO"
    assert case["updated_at"]

    # It's now persisted and readable.
    cases = client.get(f"/v1/runs/{run_id}/cases").json()["cases"]
    assert cases["INV-1"]["status"] == "IN_PROGRESS"

    # Close it.
    r = client.patch(f"/v1/runs/{run_id}/cases/INV-1", json={"status": "RESOLVED"})
    assert r.status_code == 200
    assert r.json()["case"]["status"] == "RESOLVED"

    # Each change left a CASE_UPDATE audit event (from → to).
    events = client.get(f"/v1/runs/{run_id}/audit").json()["events"]
    case_events = [e for e in events if e["event_type"] == "CASE_UPDATE"]
    assert len(case_events) == 2
    assert case_events[-1]["metadata"]["from"] == "IN_PROGRESS"
    assert case_events[-1]["metadata"]["to"] == "RESOLVED"
    assert case_events[-1]["invoice_id"] == "INV-1"


def test_case_rejects_bad_status_and_unknown_invoice(monkeypatch):
    store = _bootstrap_memory_store(monkeypatch)
    run_id = _seed_run(store)

    from fastapi.testclient import TestClient
    from app.api.main import app

    client = TestClient(app)

    assert client.patch(f"/v1/runs/{run_id}/cases/INV-1", json={"status": "BOGUS"}).status_code == 400
    assert client.patch(f"/v1/runs/{run_id}/cases/NOPE", json={"status": "RESOLVED"}).status_code == 404
