"""Per-org integrations (Phase 2a BYOK): crypto, storage, resolution, API."""
from __future__ import annotations

import json

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from starlette.requests import Request

from app.api import roles
from app.api.auth import Principal
from app.api.deps import require_permission


@pytest.fixture
def org_env(monkeypatch, tmp_path):
    """Hermetic env: a real Fernet key, per-org config on, empty provider env,
    fresh sqlite DB. Resets the cached engine + settings between cases."""
    monkeypatch.setenv("CONFIG_ENC_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("PER_ORG_CONFIG_ENABLED", "true")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path.as_posix()}/p2.db")
    for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "AZURE_OPENAI_API_KEY",
              "AZURE_CHAT_OPENAI_ENDPOINT", "SUPABASE_URL", "SUPABASE_KEY"):
        monkeypatch.setenv(k, "")
    monkeypatch.setenv("RUN_STORE_BACKEND", "memory")
    monkeypatch.setenv("DB_PERSISTENCE_ENABLED", "false")

    from app.config import get_settings
    from app.db import session as db_session
    from app.api import org_config

    get_settings.cache_clear()
    db_session.reset_engine()
    org_config._table_ensured = False
    yield
    get_settings.cache_clear()
    db_session.reset_engine()
    org_config._table_ensured = False


# --------------------------------------------------------------------------- #
# Encryption
# --------------------------------------------------------------------------- #
def test_crypto_roundtrip(org_env):
    from app.security import crypto

    assert crypto.is_configured()
    assert crypto.decrypt(crypto.encrypt("sk-secret")) == "sk-secret"


def test_crypto_requires_key(monkeypatch):
    monkeypatch.setenv("CONFIG_ENC_KEY", "")
    from app.config import get_settings
    from app.security import crypto

    get_settings.cache_clear()
    assert not crypto.is_configured()
    with pytest.raises(crypto.SecretCryptoError):
        crypto.encrypt("x")
    get_settings.cache_clear()


# --------------------------------------------------------------------------- #
# Storage + resolution
# --------------------------------------------------------------------------- #
def test_upsert_status_hides_secret(org_env):
    from app.api import org_config as oc

    oc.upsert(tenant_id="org_a", kind=oc.AI_ANTHROPIC, secret="sk-ant",
              meta={"classify_model": "claude-x"}, actor="u1")
    status = oc.list_status("org_a")
    assert len(status) == 1
    row = status[0]
    assert row["configured"] is True
    assert row["kind"] == oc.AI_ANTHROPIC
    assert "secret" not in row  # the secret must never be exposed
    assert row["meta"]["classify_model"] == "claude-x"


def test_resolve_applies_org_override(org_env):
    from app.api import org_config as oc

    oc.upsert(tenant_id="org_a", kind=oc.AI_ANTHROPIC, secret="sk-ant",
              meta={"classify_model": "claude-x", "draft_model": "claude-y"}, actor="u1")
    eff = oc.resolve_settings("org_a")
    assert eff.active_ai_provider == "anthropic"
    assert eff.anthropic_api_key == "sk-ant"
    assert eff.model_for("classify") == "claude-x"
    assert eff.model_for("draft") == "claude-y"


def test_resolve_unconfigured_org_is_env(org_env):
    from app.api import org_config as oc

    # No integration configured → falls back to env (mock, since keys empty).
    assert oc.resolve_settings("org_none").active_ai_provider == "mock"


def test_resolve_flag_off_ignores_overrides(org_env, monkeypatch):
    from app.api import org_config as oc

    oc.upsert(tenant_id="org_a", kind=oc.AI_ANTHROPIC, secret="sk-ant", meta={}, actor="u1")
    monkeypatch.setenv("PER_ORG_CONFIG_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    # Flag off → env base regardless of stored config.
    assert oc.resolve_settings("org_a").active_ai_provider == "mock"
    # …but force=True (the test endpoint) still applies it.
    assert oc.resolve_settings("org_a", force=True).active_ai_provider == "anthropic"


def test_highest_precedence_provider_wins(org_env):
    from app.api import org_config as oc

    oc.upsert(tenant_id="org_a", kind=oc.AI_GEMINI, secret="gk", meta={}, actor="u")
    oc.upsert(tenant_id="org_a", kind=oc.AI_ANTHROPIC, secret="ak", meta={}, actor="u")
    # anthropic > gemini → anthropic wins, others cleared.
    eff = oc.resolve_settings("org_a")
    assert eff.active_ai_provider == "anthropic"
    assert eff.gemini_api_key == ""


def test_branding_persists_and_resolves(org_env):
    from app.api import org_config as oc

    # Branding has no secret — configured via meta.
    oc.upsert(
        tenant_id="org_b", kind=oc.BRANDING, secret=None,
        meta={"signature_name": "Acme AP", "signature_company": "Acme Corp", "disclose_ai": True},
        actor="u",
    )
    status = {r["kind"]: r for r in oc.list_status("org_b")}
    assert status["branding"]["configured"] is True
    eff = oc.resolve_settings("org_b")
    assert eff.comms_signature_name == "Acme AP"
    assert eff.comms_signature_company == "Acme Corp"
    assert eff.comms_disclose_ai_assistance is True


def test_email_and_slack_resolve_without_leaking(org_env):
    import json

    from app.api import org_config as oc

    oc.upsert(
        tenant_id="org_c", kind=oc.EMAIL, secret="smtp-pass",
        meta={"smtp_host": "smtp.acme.com", "smtp_port": "587", "from_address": "ap@acme.com"},
        actor="u",
    )
    oc.upsert(
        tenant_id="org_c", kind=oc.SLACK, secret="https://hooks.slack.com/services/XXX",
        meta={}, actor="u",
    )
    # No secret in the status payload.
    status = oc.list_status("org_c")
    assert "smtp-pass" not in json.dumps(status)
    assert "hooks.slack.com" not in json.dumps(status)

    eff = oc.resolve_settings("org_c")
    assert eff.gmail_smtp_user == "ap@acme.com"
    assert eff.gmail_smtp_host == "smtp.acme.com"
    assert eff.gmail_smtp_port == 587
    assert eff.gmail_smtp_password == "smtp-pass"
    assert eff.slack_webhook_url == "https://hooks.slack.com/services/XXX"


def test_branding_put_needs_no_secret(org_env):
    # Branding is not a secret kind → PUT without a secret is accepted (200).
    c = _client()
    r = c.put("/v1/org/integrations/branding", json={"signature_name": "Acme"})
    assert r.status_code == 200
    body = c.get("/v1/org/integrations").json()
    assert any(i["kind"] == "branding" and i["configured"] for i in body["integrations"])


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
def _client():
    from app.api.main import app
    from fastapi.testclient import TestClient

    return TestClient(app)


def test_api_crud_never_leaks_secret(org_env):
    c = _client()
    r = c.put("/v1/org/integrations/ai_anthropic",
              json={"secret": "sk-ant-LEAKME", "classify_model": "claude-opus-4-8"})
    assert r.status_code == 200

    body = c.get("/v1/org/integrations").json()
    assert body["enc_key_configured"] is True
    assert "sk-ant-LEAKME" not in json.dumps(body)  # secret must never be returned
    assert any(i["kind"] == "ai_anthropic" and i["configured"] for i in body["integrations"])

    t = c.post("/v1/org/integrations/ai_anthropic/test").json()
    assert t["ok"] is True and t["active_provider"] == "anthropic"

    assert c.delete("/v1/org/integrations/ai_anthropic").status_code == 200
    assert c.get("/v1/org/integrations").json()["integrations"] == []


def test_api_rejects_bad_kind_and_missing_secret(org_env):
    c = _client()
    assert c.put("/v1/org/integrations/ai_bogus", json={"secret": "x"}).status_code == 400
    # First-time config without a secret is rejected.
    assert c.put("/v1/org/integrations/ai_gemini", json={"classify_model": "g"}).status_code == 422


def test_put_requires_enc_key(monkeypatch, tmp_path):
    # Auth off but no CONFIG_ENC_KEY → cannot store secrets.
    monkeypatch.setenv("CONFIG_ENC_KEY", "")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path.as_posix()}/p2b.db")
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_KEY", "")
    monkeypatch.setenv("RUN_STORE_BACKEND", "memory")
    from app.config import get_settings
    from app.db import session as db_session

    get_settings.cache_clear()
    db_session.reset_engine()
    r = _client().put("/v1/org/integrations/ai_anthropic", json={"secret": "x"})
    assert r.status_code == 400
    get_settings.cache_clear()
    db_session.reset_engine()


def test_config_write_is_admin_only():
    """A non-admin role is denied config:write."""
    dep = require_permission(roles.CONFIG_WRITE)
    clerk = Principal(subject="u", tenant_id="t", role=roles.CLERK, claims={})
    scope = {
        "type": "http", "method": "PUT", "path": "/v1/org/integrations/ai_anthropic",
        "query_string": b"", "headers": [], "scheme": "http", "server": ("t", 80),
        "path_params": {},
    }
    with pytest.raises(HTTPException) as ei:
        dep(request=Request(scope), principal=clerk)
    assert ei.value.status_code == 403
    # admin passes
    admin = Principal(subject="a", tenant_id="t", role=roles.ADMIN, claims={})
    assert dep(request=Request(scope), principal=admin) is admin
