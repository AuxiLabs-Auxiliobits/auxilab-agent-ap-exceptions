"""Per-tenant vendor directory (F1-5): store, resolver wiring, API, bulk routing."""
from __future__ import annotations

from decimal import Decimal


def _setup(monkeypatch, tmp_path):
    db = tmp_path / "vd.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db.as_posix()}")
    monkeypatch.setenv("RUN_STORE_BACKEND", "memory")
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_KEY", "")
    monkeypatch.setenv("DB_PERSISTENCE_ENABLED", "false")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.db.session import init_db, reset_engine
    reset_engine()
    init_db()
    from app.api import vendor_directory
    vendor_directory._table_ensured = False
    from app.api import store as store_mod
    store_mod.reset_store_cache()


def _teardown():
    from app.config import get_settings
    from app.db.session import reset_engine
    from app.api import store as store_mod
    reset_engine()
    store_mod.reset_store_cache()
    get_settings.cache_clear()


def test_vendor_directory_store(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    from app.api import vendor_directory as vd

    vd.upsert(tenant_id="t1", vendor_name="Acme Corp", email="ar@acme.com", contact_name="Pat")
    vd.upsert(tenant_id="t1", vendor_name="Globex", email="ap@globex.com")
    vd.upsert(tenant_id="t2", vendor_name="Acme Corp", email="other@acme.com")  # other tenant

    # Normalized, case/space-insensitive lookup.
    assert vd.get_email("t1", "acme corp") == "ar@acme.com"
    assert vd.get_email("t1", "  ACME CORP ") == "ar@acme.com"
    assert vd.get_email("t1", "Unknown") is None
    # Tenant isolation.
    assert vd.get_email("t2", "Acme Corp") == "other@acme.com"
    assert len(vd.list_contacts("t1")) == 2
    # Update in place (no dup).
    vd.upsert(tenant_id="t1", vendor_name="Acme Corp", email="new@acme.com")
    assert vd.get_email("t1", "Acme Corp") == "new@acme.com"
    assert len(vd.list_contacts("t1")) == 2
    # Delete.
    assert vd.delete("t1", "Globex") is True
    assert vd.get_email("t1", "Globex") is None
    assert vd.delete("t1", "Globex") is False
    _teardown()


def test_resolver_prefers_directory(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    from app.api import vendor_directory as vd
    vd.upsert(tenant_id="t1", vendor_name="Acme", email="ar@acme.com")

    from app.comms.recipients import resolve_recipient
    from app.config import Settings
    from app.schemas import CommChannel, CommunicationDraft
    draft = CommunicationDraft(invoice_id="INV-1", channel=CommChannel.VENDOR_EMAIL,
                               recipient_hint="x", subject="s", body="b",
                               template_id="t", model_id="m")
    s = Settings(comms_test_recipient="fallback@test.com")
    # Directory hit wins.
    assert resolve_recipient(draft=draft, settings=s, vendor_name="Acme", tenant_id="t1") == "ar@acme.com"
    # Miss falls back to the test recipient.
    assert resolve_recipient(draft=draft, settings=s, vendor_name="Nope", tenant_id="t1") == "fallback@test.com"
    # No tenant → no directory consult.
    assert resolve_recipient(draft=draft, settings=s, vendor_name="Acme") == "fallback@test.com"
    _teardown()


def test_vendor_contacts_api(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    from fastapi.testclient import TestClient
    from app.api.main import app
    c = TestClient(app)

    assert c.put("/v1/vendor-contacts",
                 json={"vendor_name": "Acme", "email": "ar@acme.com", "contact_name": "Pat"}
                 ).status_code == 200
    contacts = c.get("/v1/vendor-contacts").json()["contacts"]
    assert any(x["vendor_name"] == "Acme" and x["email"] == "ar@acme.com" for x in contacts)
    # Invalid email rejected at the schema.
    assert c.put("/v1/vendor-contacts", json={"vendor_name": "X", "email": "notanemail"}).status_code == 422
    # Delete (body via request()).
    assert c.request("DELETE", "/v1/vendor-contacts", json={"vendor_name": "Acme"}).status_code == 200
    assert c.request("DELETE", "/v1/vendor-contacts", json={"vendor_name": "Acme"}).status_code == 404
    _teardown()


def test_bulk_routes_each_vendor_to_its_email(monkeypatch, tmp_path):
    """The headline case: one upload, many vendors → each invoice goes to its own
    vendor's email; a vendor's multiple invoices consolidate into one message."""
    _setup(monkeypatch, tmp_path)
    monkeypatch.setenv("COMMS_DRYRUN", "true")
    monkeypatch.setenv("COMMS_SENT_DIR", str(tmp_path / "sent"))
    monkeypatch.delenv("VENDOR_MASTER_PATH", raising=False)
    monkeypatch.setenv("COMMS_TEST_RECIPIENT", "")  # no blanket fallback
    from app.config import get_settings
    get_settings.cache_clear()

    from app.api import vendor_directory as vd
    vd.upsert(tenant_id="default", vendor_name="Acme", email="ar@acme.com")
    vd.upsert(tenant_id="default", vendor_name="Globex", email="ap@globex.com")

    from app.api import store as store_mod
    store = store_mod.get_store()
    from app.graph.builder import initial_state
    from app.schemas import CommChannel, CommunicationDraft, ExceptionRow
    state = initial_state("run_mv", "default")
    state["status"] = "AWAITING_REVIEW"
    specs = [("INV-1", "Acme"), ("INV-2", "Acme"), ("INV-3", "Globex")]
    state["rows"] = [
        ExceptionRow(invoice_id=i, vendor_name=v, invoice_amount=Decimal("1000"),
                     po_number="PO", exception_type="Price Variance",
                     exception_description="x", days_outstanding=5)
        for i, v in specs
    ]
    state["drafts"] = [
        CommunicationDraft(invoice_id=i, channel=CommChannel.VENDOR_EMAIL,
                           recipient_hint="Vendor AR", subject=f"{i}", body=f"Please review {i}.",
                           template_id="vendor_price_variance", model_id="m")
        for i, _v in specs
    ]
    store.put(state)

    from fastapi.testclient import TestClient
    from app.api.main import app
    body = TestClient(app).post(
        "/v1/runs/run_mv/drafts/send_all",
        json={"invoice_ids": ["INV-1", "INV-2", "INV-3"]},
    ).json()

    by_id = {r["invoice_id"]: r for r in body["results"]}
    # Acme's two invoices → consolidated, one message, to ar@acme.com.
    assert by_id["INV-1"]["recipient"] == "ar@acme.com"
    assert by_id["INV-2"]["recipient"] == "ar@acme.com"
    assert by_id["INV-1"].get("consolidated") and by_id["INV-2"].get("consolidated")
    assert by_id["INV-1"]["message_id"] == by_id["INV-2"]["message_id"]
    # Globex's single invoice → its own email, not consolidated.
    assert by_id["INV-3"]["recipient"] == "ap@globex.com"
    assert not by_id["INV-3"].get("consolidated")
    assert body["summary"]["dryrun"] == 3
    _teardown()
