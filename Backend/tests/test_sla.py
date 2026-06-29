"""Tests for F1-2: operator SLA evaluation + notifications."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal


def _row(invoice_id, vendor="Acme", amount="1000", days=10):
    from app.schemas import ExceptionRow
    return ExceptionRow(
        invoice_id=invoice_id, vendor_name=vendor, invoice_amount=Decimal(amount),
        po_number="PO-1", exception_type="Price Variance",
        exception_description="x", days_outstanding=days,
    )


def _res(invoice_id, sla_hours):
    from app.schemas import ResolutionDecision, ResolutionPath
    return ResolutionDecision(
        invoice_id=invoice_id, resolution_path=ResolutionPath.ESCALATE_CONTROLLER,
        rule_id="r", rule_version="v1", rule_trace=["t"],
        requires_communication=True, sla_hours=sla_hours,
    )


# --------------------------------------------------------------------------- #
# Pure SLA evaluation
# --------------------------------------------------------------------------- #
def test_evaluate_sla_classifies_and_counts():
    from app.comms.sla import evaluate_sla
    from app.schemas import PriorityBucket, PriorityEntry, PriorityQueues

    # SLA clock anchored to invoice-received time (run created − days_outstanding).
    now = datetime(2026, 6, 17, 12, 0, tzinfo=UTC)
    created = now
    state = {
        "created_at": created,
        "rows": [
            _row("INV-1", days=1),  # received now − 24h
            _row("INV-2", days=0),  # received now
            _row("INV-3", days=1),  # received now − 24h
        ],
        "resolutions": [
            _res("INV-1", 8),    # deadline now−16h -> breached (16h overdue)
            _res("INV-2", 24),   # deadline now+24h -> ok
            _res("INV-3", 26),   # deadline now+2h  -> due_soon (within 4h)
        ],
        "drafts": [],
        "priority_queues": PriorityQueues(
            high=[PriorityEntry(invoice_id="INV-1", priority_score=0.9,
                                bucket=PriorityBucket.HIGH, drivers=[])],
        ),
    }
    rep = evaluate_sla(state, now=now, due_soon_hours=4.0)
    assert rep["total_open"] == 3
    assert rep["breached"] == 1
    assert rep["due_soon"] == 1
    assert rep["high_waiting"] == 1
    assert rep["breached_items"][0]["invoice_id"] == "INV-1"
    assert rep["breached_items"][0]["hours_overdue"] == 16.0


def test_send_sla_digest_skipped_without_mailbox():
    from app.comms import operator_notify
    from app.config import Settings
    report = {"total_open": 1, "high_waiting": 1, "breached": 1, "due_soon": 0,
              "breached_items": [], "due_soon_items": []}
    s = Settings(comms_ap_team_mailbox="", comms_finance_controller_mailbox="", gmail_smtp_user="")
    out = operator_notify.send_sla_digest(run_id="r", report=report, settings=s)
    assert out["status"] == "skipped"


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
def _seed_run(store, *, created):
    from app.graph.builder import initial_state
    state = initial_state("run_sla", "default")
    state["status"] = "AWAITING_REVIEW"
    state["created_at"] = created
    state["rows"] = [_row("INV-1")]
    state["resolutions"] = [_res("INV-1", 8)]
    store.put(state)


def test_sla_endpoint_and_operator_notify(monkeypatch, tmp_path):
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
    _seed_run(store, created=datetime.now(UTC) - timedelta(hours=10))

    from fastapi.testclient import TestClient
    from app.api.main import app
    client = TestClient(app)

    # GET /sla reports the breach.
    r = client.get("/v1/runs/run_sla/sla")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_open"] == 1 and body["breached"] == 1
    assert body["breached_items"][0]["invoice_id"] == "INV-1"

    # POST /notify sends a dry-run operator digest to the AP mailbox.
    r2 = client.post("/v1/runs/run_sla/notify")
    assert r2.status_code == 200, r2.text
    n = r2.json()
    assert n["notification"]["status"] == "dryrun"
    assert n["notification"]["recipient"] == "ops@example.com"
    assert n["summary"]["breached"] == 1

    store_mod.reset_store_cache()
    get_settings.cache_clear()
