"""Subscriber storage, unsubscribe, and the token-gated newsletter bulk send."""
from __future__ import annotations

import pytest


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("CONTACT_DRYRUN", "true")
    monkeypatch.setenv("CONTACT_RECIPIENT", "ops@example.com")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path.as_posix()}/n.db")
    monkeypatch.setenv("NEWSLETTER_ADMIN_TOKEN", "secret-token")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://app.example.com")
    for k in ("SUPABASE_URL", "SUPABASE_KEY", "GMAIL_SMTP_USER", "GMAIL_SMTP_PASSWORD"):
        monkeypatch.setenv(k, "")
    monkeypatch.setenv("RUN_STORE_BACKEND", "memory")
    from app.api import subscribers
    from app.config import get_settings
    from app.db import session as db_session

    get_settings.cache_clear()
    db_session.reset_engine()
    subscribers._table_ensured = False
    yield
    get_settings.cache_clear()
    db_session.reset_engine()
    subscribers._table_ensured = False


def _client():
    from fastapi.testclient import TestClient

    from app.api.main import app

    return TestClient(app)


def test_subscribe_stores_and_dedupes(env):
    from app.api import subscribers

    c = _client()
    assert c.post("/v1/subscribe", json={"email": "a@b.com"}).json()["subscribed"] is True
    c.post("/v1/subscribe", json={"email": "A@b.com"})  # same email, different case
    assert subscribers.counts() == {"active": 1, "total": 1, "unsubscribed": 0}


def test_subscribe_validates_email(env):
    assert _client().post("/v1/subscribe", json={"email": "nope"}).status_code == 422


def test_unsubscribe_flow(env):
    from app.api import subscribers

    token, created = subscribers.add("z@b.com")
    assert created is True
    r = _client().get("/v1/unsubscribe", params={"token": token})
    assert r.status_code == 200 and "unsubscribed" in r.text.lower()
    assert subscribers.list_active() == []
    # A bad token still returns a friendly page (no leak).
    assert _client().get("/v1/unsubscribe", params={"token": "bogus"}).status_code == 200


def test_newsletter_requires_token(env):
    c = _client()
    # No token header → 403.
    assert c.post("/v1/newsletter", json={"subject": "Hi", "body": "x"}).status_code == 403
    # Wrong token → 403.
    assert c.post(
        "/v1/newsletter", json={"subject": "Hi", "body": "x"},
        headers={"X-Newsletter-Token": "wrong"},
    ).status_code == 403


def test_newsletter_dry_run_counts(env):
    from app.api import subscribers

    subscribers.add("a@b.com")
    subscribers.add("c@d.com")
    r = _client().post(
        "/v1/newsletter",
        json={"subject": "June", "body": "Hello", "dry_run": True},
        headers={"X-Newsletter-Token": "secret-token"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["recipients"] == 2 and body["dry_run"] is True


def test_newsletter_stats_and_preview(env):
    from app.api import subscribers

    subscribers.add("a@b.com")
    c = _client()
    h = {"X-Newsletter-Token": "secret-token"}
    stats = c.get("/v1/newsletter/stats", headers=h)
    assert stats.status_code == 200 and stats.json()["active"] == 1
    # token-gating on stats
    assert c.get("/v1/newsletter/stats").status_code == 403
    # preview renders HTML with an unsubscribe link, sends nothing
    pv = c.post("/v1/newsletter/preview", json={"subject": "Hi", "body": "Hello"}, headers=h)
    assert pv.status_code == 200
    html = pv.json()["html"]
    assert "<!DOCTYPE html>" in html and "unsubscribe" in html.lower()


def test_newsletter_real_send_bulk(monkeypatch, env):
    monkeypatch.setenv("GMAIL_SMTP_USER", "agent@example.com")
    monkeypatch.setenv("GMAIL_SMTP_PASSWORD", "app-pass")
    from app.config import get_settings

    get_settings.cache_clear()
    from app.api import subscribers

    subscribers.add("a@b.com")
    subscribers.add("c@d.com")

    captured: dict = {}

    def fake_bulk(*, messages, settings):
        captured["messages"] = messages
        return [{"to": m["to"], "ok": True} for m in messages]

    import app.api.routes_contact as rc
    monkeypatch.setattr(rc, "send_bulk_emails", fake_bulk)

    r = _client().post(
        "/v1/newsletter",
        json={"subject": "June", "body": "Hello subscribers"},
        headers={"X-Newsletter-Token": "secret-token"},
    )
    assert r.status_code == 200
    assert r.json()["sent"] == 2
    # Each message carries an unsubscribe link in its HTML.
    assert all("unsubscribe" in m["html"].lower() for m in captured["messages"])
    assert all("app.example.com/v1/unsubscribe" in m["html"] for m in captured["messages"])
