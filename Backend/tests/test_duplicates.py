"""Cross-run / historical duplicate detection (GET /v1/runs/{id}/duplicates).

An invoice_id that appears in another run of the same tenant is flagged as a
possible double-pay, with each prior occurrence and whether the amount matches.
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


def _row(inv: str, amount: str, vendor: str = "Acme"):
    from app.schemas.exception_row import ExceptionRow

    return ExceptionRow(
        invoice_id=inv,
        vendor_name=vendor,
        invoice_amount=Decimal(amount),
        exception_type="Price Variance",
        exception_description="desc",
        days_outstanding=10,
    )


def test_cross_run_duplicate_detection(monkeypatch):
    store = _bootstrap_memory_store(monkeypatch)
    from app.graph.builder import initial_state

    old = initial_state("run_old", "default")
    old["created_at"] = "2026-06-01T00:00:00Z"
    old["rows"] = [_row("INV-1", "100"), _row("INV-2", "200")]
    store.put(old)

    new = initial_state("run_new", "default")
    new["created_at"] = "2026-06-20T00:00:00Z"
    # INV-2 repeats with the SAME amount (true double); INV-1 repeats with a
    # DIFFERENT amount; INV-3 / INV-9 are unique to this run.
    new["rows"] = [
        _row("INV-2", "200"),
        _row("INV-3", "300"),
        _row("INV-9", "999"),
        _row("INV-1", "150"),
    ]
    store.put(new)

    from fastapi.testclient import TestClient
    from app.api.main import app

    r = TestClient(app).get("/v1/runs/run_new/duplicates")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["checked"] == 4
    assert body["runs_scanned"] == 1
    assert body["duplicate_count"] == 2

    by_id = {d["invoice_id"]: d for d in body["duplicates"]}
    assert set(by_id) == {"INV-1", "INV-2"}  # INV-3 / INV-9 are not flagged

    # The current run is never matched against itself.
    inv2 = by_id["INV-2"]
    assert inv2["occurrences"][0]["run_id"] == "run_old"
    assert inv2["occurrences"][0]["amount_matches"] is True

    inv1 = by_id["INV-1"]
    assert inv1["occurrences"][0]["amount_matches"] is False  # 150 vs 100


def test_no_duplicates_when_only_one_run(monkeypatch):
    store = _bootstrap_memory_store(monkeypatch)
    from app.graph.builder import initial_state

    only = initial_state("run_solo", "default")
    only["created_at"] = "2026-06-20T00:00:00Z"
    only["rows"] = [_row("INV-1", "100"), _row("INV-2", "200")]
    store.put(only)

    from fastapi.testclient import TestClient
    from app.api.main import app

    body = TestClient(app).get("/v1/runs/run_solo/duplicates").json()
    assert body["runs_scanned"] == 0
    assert body["duplicate_count"] == 0
    assert body["duplicates"] == []
