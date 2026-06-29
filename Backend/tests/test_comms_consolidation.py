"""Bulk-send consolidation: coalesce same-recipient invoices into ONE email."""
from __future__ import annotations

from decimal import Decimal


def _memory_store(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("RUN_STORE_BACKEND", "memory")
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_KEY", "")
    monkeypatch.setenv("DB_PERSISTENCE_ENABLED", "false")
    monkeypatch.setenv("COMMS_DRYRUN", "true")
    monkeypatch.setenv("COMMS_TEST_RECIPIENT", "ar@vendor.com")  # all vendor mail → here
    monkeypatch.delenv("VENDOR_MASTER_PATH", raising=False)  # no master → fall back to test recipient
    monkeypatch.setenv("COMMS_SENT_DIR", str(tmp_path / "sent"))
    from app.config import get_settings
    get_settings.cache_clear()
    from app.api import store as store_mod
    store_mod.reset_store_cache()
    return store_mod, store_mod.get_store()


def _seed_bulk(store, n=3):
    from app.graph.builder import initial_state
    from app.schemas import CommChannel, CommunicationDraft, ExceptionRow
    state = initial_state("run_bulk", "default")
    state["status"] = "AWAITING_REVIEW"
    state["rows"] = [
        ExceptionRow(invoice_id=f"INV-{i}", vendor_name="Acme",
                     invoice_amount=Decimal("1000"), po_number="PO",
                     exception_type="Price Variance", exception_description="x",
                     days_outstanding=5)
        for i in range(1, n + 1)
    ]
    state["drafts"] = [
        CommunicationDraft(invoice_id=f"INV-{i}", channel=CommChannel.VENDOR_EMAIL,
                           recipient_hint="Vendor AR", subject=f"Invoice INV-{i}",
                           body=f"Please review INV-{i}.", template_id="vendor_price_variance",
                           model_id="m")
        for i in range(1, n + 1)
    ]
    store.put(state)


def test_render_consolidated_lists_all_invoices():
    from app.comms.email_template import render_consolidated
    from app.config import Settings
    from app.schemas import CommChannel
    items = [
        {"invoice_id": "INV-1", "vendor_name": "Acme", "amount": 1200.0,
         "issue": "Price variance", "subject": "INV-1 dispute", "body": "Please review."},
        {"invoice_id": "INV-2", "vendor_name": "Acme", "amount": 300.0,
         "issue": "Missing PO", "subject": "INV-2 PO", "body": "Send the PO."},
    ]
    text, html = render_consolidated(channel=CommChannel.VENDOR_EMAIL, items=items, settings=Settings())
    assert "2 invoice" in text.lower()
    for token in ("INV-1", "INV-2", "Please review", "Send the PO"):
        assert token in text and token in html


def test_send_all_consolidates_same_recipient(monkeypatch, tmp_path):
    store_mod, store = _memory_store(monkeypatch, tmp_path)
    _seed_bulk(store, n=3)

    from fastapi.testclient import TestClient
    from app.api.main import app
    r = TestClient(app).post(
        "/v1/runs/run_bulk/drafts/send_all",
        json={"invoice_ids": ["INV-1", "INV-2", "INV-3"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # All three invoices reported, all dry-run, all marked consolidated.
    assert body["summary"]["dryrun"] == 3
    assert body["summary"]["consolidated_invoices"] == 3
    assert all(x.get("consolidated") for x in body["results"])
    # ONE email: a single shared message id, and exactly one consolidated preview.
    assert len({x["message_id"] for x in body["results"]}) == 1
    files = list((tmp_path / "sent" / "run_bulk").glob("consolidated__*.eml"))
    assert len(files) == 1

    store_mod.reset_store_cache()
    from app.config import get_settings
    get_settings.cache_clear()


def test_send_all_consolidate_false_sends_per_invoice(monkeypatch, tmp_path):
    store_mod, store = _memory_store(monkeypatch, tmp_path)
    _seed_bulk(store, n=3)

    from fastapi.testclient import TestClient
    from app.api.main import app
    r = TestClient(app).post(
        "/v1/runs/run_bulk/drafts/send_all",
        json={"invoice_ids": ["INV-1", "INV-2", "INV-3"], "consolidate": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"]["dryrun"] == 3
    assert body["summary"]["consolidated_invoices"] == 0
    # Three separate emails: three distinct message ids, no consolidated preview.
    assert len({x["message_id"] for x in body["results"]}) == 3
    assert not list((tmp_path / "sent" / "run_bulk").glob("consolidated__*.eml"))

    store_mod.reset_store_cache()
    from app.config import get_settings
    get_settings.cache_clear()
