"""Contact-form endpoint tests (new HTML send path; CONTACT_DRYRUN-gated)."""
from __future__ import annotations

import pytest


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("CONTACT_DRYRUN", "true")
    monkeypatch.setenv("CONTACT_RECIPIENT", "ops@example.com")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path.as_posix()}/c.db")
    for k in ("SUPABASE_URL", "SUPABASE_KEY", "GMAIL_SMTP_USER", "GMAIL_SMTP_PASSWORD"):
        monkeypatch.setenv(k, "")
    monkeypatch.setenv("DB_PERSISTENCE_ENABLED", "false")
    monkeypatch.setenv("RUN_STORE_BACKEND", "memory")
    from app.api import subscribers
    from app.config import get_settings
    from app.db import session as db_session

    get_settings.cache_clear()
    db_session.reset_engine()
    subscribers._table_ensured = False
    from fastapi.testclient import TestClient

    from app.api.main import app

    yield TestClient(app)
    get_settings.cache_clear()
    db_session.reset_engine()
    subscribers._table_ensured = False


def test_contact_dryrun_logs_not_delivered(client):
    r = client.post("/v1/contact", json={
        "name": "Kate", "email": "k@x.com", "subject": "Demo", "message": "Please call me",
    })
    assert r.status_code == 200
    assert r.json()["delivered"] is False


def test_contact_honeypot_silently_dropped(client):
    r = client.post("/v1/contact", json={"message": "spam", "company_website": "bot.example"})
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_contact_requires_message(client):
    assert client.post("/v1/contact", json={"message": "   "}).status_code == 422


def test_contact_real_send_invokes_sender_and_autoreply(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("CONTACT_DRYRUN", "false")
    monkeypatch.setenv("CONTACT_RECIPIENT", "ops@example.com")
    monkeypatch.setenv("GMAIL_SMTP_USER", "agent@example.com")
    monkeypatch.setenv("GMAIL_SMTP_PASSWORD", "app-pass")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path.as_posix()}/c2.db")
    for k in ("SUPABASE_URL", "SUPABASE_KEY"):
        monkeypatch.setenv(k, "")
    monkeypatch.setenv("RUN_STORE_BACKEND", "memory")
    from app.config import get_settings

    get_settings.cache_clear()

    sent: list[dict] = []

    def fake_send(*, to, subject, text, html=None, settings, reply_to=None):
        sent.append({"to": to, "subject": subject, "reply_to": reply_to})
        return ("<id>", "250 OK")

    import app.api.routes_contact as rc
    monkeypatch.setattr(rc, "send_simple_email", fake_send)

    from fastapi.testclient import TestClient

    from app.api.main import app

    r = TestClient(app).post("/v1/contact", json={
        "name": "Kate", "email": "kate@x.com", "subject": "Demo", "message": "Call me",
    })
    assert r.status_code == 200 and r.json()["delivered"] is True
    tos = [m["to"] for m in sent]
    assert "ops@example.com" in tos       # internal notification
    assert "kate@x.com" in tos            # auto-reply to the submitter
    get_settings.cache_clear()


def test_contact_503_when_unconfigured(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("CONTACT_DRYRUN", "false")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path.as_posix()}/c3.db")
    for k in ("CONTACT_RECIPIENT", "GMAIL_SMTP_USER", "GMAIL_SMTP_PASSWORD",
              "COMMS_AP_TEAM_MAILBOX", "SUPABASE_URL", "SUPABASE_KEY"):
        monkeypatch.setenv(k, "")
    monkeypatch.setenv("RUN_STORE_BACKEND", "memory")
    from app.config import get_settings

    get_settings.cache_clear()
    from fastapi.testclient import TestClient

    from app.api.main import app

    assert TestClient(app).post("/v1/contact", json={"message": "hi"}).status_code == 503
    get_settings.cache_clear()
