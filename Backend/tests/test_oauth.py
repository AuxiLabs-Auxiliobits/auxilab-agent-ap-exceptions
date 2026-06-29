"""OAuth scaffold tests: signed state, URL building, OAuth-mode resolution.

Live token exchange (Google/Slack) needs real OAuth apps and is not tested here;
these cover everything up to the network call.
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("CONFIG_ENC_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("PER_ORG_CONFIG_ENABLED", "true")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path.as_posix()}/oauth.db")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", "https://app.example/integrations/google/callback")
    # Pin comms + provider secrets empty so the developer's real .env can't leak in.
    for k in ("SUPABASE_URL", "SUPABASE_KEY", "GMAIL_SMTP_USER", "GMAIL_SMTP_PASSWORD",
              "SLACK_WEBHOOK_URL", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "AZURE_OPENAI_API_KEY"):
        monkeypatch.setenv(k, "")
    monkeypatch.setenv("RUN_STORE_BACKEND", "memory")
    from app.api import org_config
    from app.config import get_settings
    from app.db import session as db_session

    get_settings.cache_clear()
    db_session.reset_engine()
    org_config._table_ensured = False
    yield
    get_settings.cache_clear()
    db_session.reset_engine()
    org_config._table_ensured = False


def test_state_sign_verify_roundtrip(env):
    from app.security import oauth_state

    tok = oauth_state.sign({"t": "org_1", "k": "email"})
    body = oauth_state.verify(tok)
    assert body["t"] == "org_1" and body["k"] == "email"


def test_state_rejects_tamper_and_expiry(env):
    from app.security import oauth_state

    tok = oauth_state.sign({"t": "org_1"})
    with pytest.raises(oauth_state.OAuthStateError):
        oauth_state.verify(tok[:-2] + "zz")  # corrupt signature
    with pytest.raises(oauth_state.OAuthStateError):
        oauth_state.verify(tok, max_age_seconds=-1)  # already expired


def test_google_auth_url_has_scope_and_state(env):
    from app.comms import oauth
    from app.config import get_settings

    url = oauth.google_auth_url(get_settings(), "STATE123")
    assert url.startswith("https://accounts.google.com/")
    assert "gmail.send" in url and "state=STATE123" in url and "access_type=offline" in url


def test_resolve_oauth_modes(env):
    from app.api import org_config as oc

    oc.upsert(tenant_id="org_1", kind=oc.EMAIL, secret="refresh-tok",
              meta={"mode": "oauth", "from_address": "ap@org.com"}, actor="u")
    oc.upsert(tenant_id="org_1", kind=oc.SLACK, secret="xoxb-123",
              meta={"mode": "oauth", "channel": "C9"}, actor="u")
    eff = oc.resolve_settings("org_1")
    # OAuth tokens layered in; SMTP password / webhook left empty.
    assert eff.gmail_oauth_refresh_token == "refresh-tok"
    assert eff.gmail_smtp_user == "ap@org.com"
    assert eff.gmail_smtp_password == ""
    assert eff.slack_bot_token == "xoxb-123"
    assert eff.slack_channel == "C9"
    assert eff.slack_webhook_url == ""


def test_connect_endpoints(env):
    from fastapi.testclient import TestClient

    from app.api.main import app

    c = TestClient(app)
    g = c.get("/v1/integrations/google/connect")
    assert g.status_code == 200 and "accounts.google.com" in g.json()["auth_url"]
    # Slack not configured on the server → 400.
    assert c.get("/v1/integrations/slack/connect").status_code == 400


def test_callback_rejects_bad_state(env):
    from fastapi.testclient import TestClient

    from app.api.main import app

    c = TestClient(app)
    r = c.post("/v1/integrations/google/callback", json={"code": "x", "state": "tampered.sig"})
    assert r.status_code == 400
