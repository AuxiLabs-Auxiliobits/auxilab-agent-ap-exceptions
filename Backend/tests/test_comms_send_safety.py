"""Send-safety regression tests for the comms dispatch path.

Covers three fixes:
  C1 — send_all de-duplicates invoice ids so a repeated id can't double-send.
  H1 — the per-domain daily cap is scoped per tenant (no cross-tenant bleed).
  M1 — the dry-run preview renders with the tenant-resolved settings, not env.
"""
from __future__ import annotations

from datetime import UTC, datetime


# --------------------------------------------------------------------------- #
# C1 — send_all de-dup
# --------------------------------------------------------------------------- #
def test_send_all_dedupes_duplicate_invoice_ids(monkeypatch):
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

    from app.graph.builder import initial_state
    from app.schemas import CommChannel, CommunicationDraft

    state = initial_state("run_dd", "default")
    state["status"] = "AWAITING_REVIEW"
    state["drafts"] = [
        CommunicationDraft(
            invoice_id="INV-1", channel=CommChannel.VENDOR_EMAIL,
            recipient_hint="Vendor AR", subject="s", body="b",
            template_id="t", model_id="m",
        )
    ]
    store.put(state)

    # Count dispatch invocations without sending anything real.
    import app.api.routes_comms as rc
    from app.comms.dispatcher import SendResult
    from app.schemas import SendStatus

    calls: list[str] = []

    def fake_dispatch(*, draft, run_id, **kwargs):
        calls.append(draft.invoice_id)
        return SendResult(
            invoice_id=draft.invoice_id, status=SendStatus.SENT, provider="dryrun",
            message_id="m1", recipient="v@x.com", sent_at=datetime.now(UTC),
        )

    monkeypatch.setattr(rc, "dispatch", fake_dispatch)

    from fastapi.testclient import TestClient
    from app.api.main import app

    r = TestClient(app).post(
        "/v1/runs/run_dd/drafts/send_all", json={"invoice_ids": ["INV-1", "INV-1"]}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Dispatched once, not twice, despite the duplicated id.
    assert calls == ["INV-1"]
    assert len(body["results"]) == 1
    assert body["summary"]["sent"] == 1

    store_mod.reset_store_cache()
    get_settings.cache_clear()


# --------------------------------------------------------------------------- #
# H1 — per-tenant daily cap
# --------------------------------------------------------------------------- #
def test_daily_cap_is_per_tenant(monkeypatch):
    monkeypatch.setenv("COMMS_DRYRUN", "false")
    monkeypatch.setenv("COMMS_TEST_RECIPIENT", "vendor@example.com")
    monkeypatch.setenv("COMMS_ALLOWED_DOMAINS", "")  # allow all
    monkeypatch.setenv("COMMS_PER_DOMAIN_DAILY_CAP", "1")
    monkeypatch.setenv("GMAIL_SMTP_USER", "agent@example.com")
    monkeypatch.setenv("DB_PERSISTENCE_ENABLED", "false")  # exercise the in-process cap
    from app.config import get_settings
    get_settings.cache_clear()

    import app.comms.dispatcher as disp
    disp.reset_domain_cap()
    monkeypatch.setattr(
        disp, "send_email_via_gmail",
        lambda *, draft, recipient, settings, bcc: ("<id>", "ok"),
    )

    from app.schemas import CommChannel, CommunicationDraft, SendStatus

    def _draft(i):
        return CommunicationDraft(
            invoice_id=f"INV-{i}", channel=CommChannel.VENDOR_EMAIL,
            recipient_hint="Vendor AR contact", subject="s", body="b",
            template_id="vendor_price_variance", model_id="m",
        )

    # Tenant A: cap=1 → first sends, second is capped.
    a1 = disp.dispatch(draft=_draft(1), run_id="rA", tenant_id="A")
    a2 = disp.dispatch(draft=_draft(2), run_id="rA", tenant_id="A")
    # Tenant B has its OWN quota — not consumed by A.
    b1 = disp.dispatch(draft=_draft(3), run_id="rB", tenant_id="B")

    assert a1.status == SendStatus.SENT
    assert a2.status == SendStatus.SKIPPED and "cap" in (a2.error_message or "").lower()
    assert b1.status == SendStatus.SENT

    get_settings.cache_clear()


# --------------------------------------------------------------------------- #
# P0-1 — DB-backed distributed daily send cap (reserve/release)
# --------------------------------------------------------------------------- #
def test_cap_selection_by_persistence():
    from app.comms.dispatcher import _DB_CAP, _DOMAIN_CAP, _cap_for
    from app.config import Settings
    assert _cap_for(Settings(db_persistence_enabled=True)) is _DB_CAP
    assert _cap_for(Settings(db_persistence_enabled=False)) is _DOMAIN_CAP


def test_db_daily_cap_reserve_release(monkeypatch, tmp_path):
    """Atomic conditional increment: reserve up to cap, block beyond, release a
    slot, per-tenant isolation, and cap<=0 = unlimited."""
    db = tmp_path / "cap.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db.as_posix()}")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.db.session import init_db, reset_engine
    reset_engine()
    init_db()

    from app.comms.dispatcher import _DbDailyCap
    cap = _DbDailyCap()
    day = "2026-06-17"

    # cap = 2 → two reserves win, the third is blocked.
    assert cap.reserve(tenant_id="A", domain="x.com", day_iso=day, cap=2) is True
    assert cap.reserve(tenant_id="A", domain="x.com", day_iso=day, cap=2) is True
    assert cap.reserve(tenant_id="A", domain="x.com", day_iso=day, cap=2) is False
    # Releasing one frees a slot.
    cap.release(tenant_id="A", domain="x.com", day_iso=day)
    assert cap.reserve(tenant_id="A", domain="x.com", day_iso=day, cap=2) is True
    # A different tenant has its own quota.
    assert cap.reserve(tenant_id="B", domain="x.com", day_iso=day, cap=2) is True
    # cap <= 0 means unlimited (no DB write).
    assert cap.reserve(tenant_id="A", domain="x.com", day_iso=day, cap=0) is True

    reset_engine()
    get_settings.cache_clear()


# --------------------------------------------------------------------------- #
# M1 — dry-run uses the passed (tenant) settings, not env
# --------------------------------------------------------------------------- #
def test_dryrun_honors_passed_settings(tmp_path):
    from app.comms.providers.dryrun import send_dryrun
    from app.config import Settings
    from app.schemas import CommChannel, CommunicationDraft

    draft = CommunicationDraft(
        invoice_id="INV-9", channel=CommChannel.VENDOR_EMAIL,
        recipient_hint="x", subject="s", body="b", template_id="t", model_id="m",
    )
    # Passed settings disable HTML — the env default is True, so if the preview
    # used get_settings() it would still write an .html file.
    s = Settings(comms_email_html_enabled=False)
    _msg_id, base = send_dryrun(
        draft=draft, recipient="v@x.com", run_id="r9",
        sent_dir=tmp_path, sender="a@b.com", bcc=None, settings=s,
    )
    assert base.with_suffix(".eml").exists()
    assert not base.with_suffix(".html").exists()


# --------------------------------------------------------------------------- #
# H2 — atomic claim guards against concurrent double-send
# --------------------------------------------------------------------------- #
def _memory_store(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("RUN_STORE_BACKEND", "memory")
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_KEY", "")
    monkeypatch.setenv("DB_PERSISTENCE_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    from app.api import store as store_mod
    store_mod.reset_store_cache()
    return store_mod, store_mod.get_store()


def _seed(store, *, status):
    from app.graph.builder import initial_state
    from app.schemas import CommChannel, CommunicationDraft, SendStatus

    state = initial_state("run_h2", "default")
    state["status"] = "AWAITING_REVIEW"
    state["drafts"] = [
        CommunicationDraft(
            invoice_id="INV-1", channel=CommChannel.VENDOR_EMAIL,
            recipient_hint="Vendor AR", subject="s", body="b",
            template_id="t", model_id="m",
            send_status=status,
            send_message_id="<prior>" if status == SendStatus.SENT else None,
            send_provider="gmail_smtp" if status == SendStatus.SENT else None,
        )
    ]
    store.put(state)


def test_claim_draft_for_send_is_single(monkeypatch):
    from app.schemas import SendStatus
    store_mod, store = _memory_store(monkeypatch)
    _seed(store, status=SendStatus.DRAFT)

    # First claim wins; a second concurrent claim loses (now SENDING).
    assert store.claim_draft_for_send("run_h2", "INV-1") is True
    assert store.claim_draft_for_send("run_h2", "INV-1") is False
    # An already-SENT draft is never claimable.
    store_mod.reset_store_cache()
    store = store_mod.get_store()
    _seed(store, status=SendStatus.SENT)
    assert store.claim_draft_for_send("run_h2", "INV-1") is False

    store_mod.reset_store_cache()


def test_send_draft_conflicts_when_in_flight(monkeypatch):
    from app.schemas import SendStatus
    store_mod, store = _memory_store(monkeypatch)
    _seed(store, status=SendStatus.SENDING)  # a send is already in flight

    import app.api.routes_comms as rc
    called = []
    monkeypatch.setattr(rc, "dispatch", lambda **kw: called.append(1))

    from fastapi.testclient import TestClient
    from app.api.main import app
    r = TestClient(app).post("/v1/runs/run_h2/drafts/INV-1/send")
    assert r.status_code == 409
    assert called == []  # never dispatched
    store_mod.reset_store_cache()


def _seed_sending(store, claimed_at):
    from app.graph.builder import initial_state
    from app.schemas import CommChannel, CommunicationDraft, SendStatus
    state = initial_state("run_h2", "default")
    state["status"] = "AWAITING_REVIEW"
    state["drafts"] = [
        CommunicationDraft(
            invoice_id="INV-1", channel=CommChannel.VENDOR_EMAIL, recipient_hint="x",
            subject="s", body="b", template_id="t", model_id="m",
            send_status=SendStatus.SENDING, send_claimed_at=claimed_at,
        )
    ]
    store.put(state)


def test_claimable_for_send_helper():
    from datetime import UTC, datetime, timedelta
    from app.schemas import SendStatus, claimable_for_send
    now = datetime.now(UTC)
    assert claimable_for_send(SendStatus.DRAFT, None, now, 120) is True
    assert claimable_for_send(SendStatus.FAILED, None, now, 120) is True
    assert claimable_for_send(SendStatus.SKIPPED, None, now, 120) is True
    assert claimable_for_send(SendStatus.SENT, None, now, 120) is False
    assert claimable_for_send(SendStatus.DRYRUN, None, now, 120) is False
    # SENDING: a recent claim holds; only a stale TIMESTAMPED claim is reclaimable.
    assert claimable_for_send(SendStatus.SENDING, now, now, 120) is False
    assert claimable_for_send(SendStatus.SENDING, now - timedelta(seconds=200), now, 120) is True
    # No claim timestamp = treated as in-flight (real claims always stamp it).
    assert claimable_for_send(SendStatus.SENDING, None, now, 120) is False
    # force=True (explicit operator resend) additionally reclaims a terminal
    # SENT/DRYRUN draft, but still NOT a live in-flight SENDING claim.
    assert claimable_for_send(SendStatus.SENT, None, now, 120, force=True) is True
    assert claimable_for_send(SendStatus.DRYRUN, None, now, 120, force=True) is True
    assert claimable_for_send(SendStatus.SENDING, now, now, 120, force=True) is False


def test_send_claim_ttl_reclaims_stale(monkeypatch):
    """A live SENDING claim holds; a stale one (worker died mid-send) self-heals."""
    from datetime import UTC, datetime, timedelta
    from app.config import get_settings
    store_mod, store = _memory_store(monkeypatch)
    ttl = get_settings().comms_send_claim_ttl_seconds

    _seed_sending(store, datetime.now(UTC))                       # fresh claim
    assert store.claim_draft_for_send("run_h2", "INV-1") is False  # not reclaimable
    _seed_sending(store, datetime.now(UTC) - timedelta(seconds=ttl + 5))  # stale
    assert store.claim_draft_for_send("run_h2", "INV-1") is True   # reclaimed
    store_mod.reset_store_cache()


def test_send_draft_idempotent_when_already_sent(monkeypatch):
    from app.schemas import SendStatus
    store_mod, store = _memory_store(monkeypatch)
    _seed(store, status=SendStatus.SENT)

    import app.api.routes_comms as rc
    called = []
    monkeypatch.setattr(rc, "dispatch", lambda **kw: called.append(1))

    from fastapi.testclient import TestClient
    from app.api.main import app
    r = TestClient(app).post("/v1/runs/run_h2/drafts/INV-1/send")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "sent"
    assert body["message_id"] == "<prior>"
    assert called == []  # idempotent — did NOT re-send
    store_mod.reset_store_cache()


def test_resend_reresolves_updated_vendor_email(monkeypatch):
    """An explicit resend re-resolves the recipient from the vendor directory,
    so an EDITED vendor email is used instead of the address sent last time.

    Regression for: update vendor email → Resend went to the stale address."""
    monkeypatch.setenv("COMMS_DRYRUN", "true")
    store_mod, store = _memory_store(monkeypatch)
    from app.config import get_settings
    get_settings.cache_clear()  # pick up COMMS_DRYRUN

    from app.graph.builder import initial_state
    from app.schemas import CommChannel, CommunicationDraft, SendStatus

    state = initial_state("run_h2", "default")
    state["status"] = "AWAITING_REVIEW"
    state["drafts"] = [
        CommunicationDraft(
            invoice_id="INV-1", channel=CommChannel.VENDOR_EMAIL,
            recipient_hint="Vendor AR", subject="s", body="b",
            template_id="t", model_id="m",
            send_status=SendStatus.SENT, send_provider="gmail_smtp",
            send_message_id="<prior>", recipient="old@vendor.com",
        )
    ]
    store.put(state)

    # The vendor's email was updated in the directory after the first send.
    from app.api import vendor_directory
    monkeypatch.setattr(vendor_directory, "get_email", lambda tenant, vendor: "new@vendor.com")

    from fastapi.testclient import TestClient
    from app.api.main import app
    client = TestClient(app)

    # A plain send stays idempotent — it replays the original recipient and
    # never re-resolves.
    r_plain = client.post("/v1/runs/run_h2/drafts/INV-1/send")
    assert r_plain.status_code == 200, r_plain.text
    assert r_plain.json()["recipient"] == "old@vendor.com"

    # An explicit resend re-resolves → the UPDATED vendor email is used.
    r_resend = client.post("/v1/runs/run_h2/drafts/INV-1/send", json={"resend": True})
    assert r_resend.status_code == 200, r_resend.text
    body = r_resend.json()
    assert body["status"] == "dryrun"
    assert body["recipient"] == "new@vendor.com"

    store_mod.reset_store_cache()
    get_settings.cache_clear()
