"""Communication preview endpoint tests (read-only rendering, no sending)."""
from __future__ import annotations

import pytest


@pytest.fixture
def client(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "AZURE_OPENAI_API_KEY",
              "AZURE_CHAT_OPENAI_ENDPOINT", "SUPABASE_URL", "SUPABASE_KEY"):
        monkeypatch.setenv(k, "")
    monkeypatch.setenv("DB_PERSISTENCE_ENABLED", "false")
    monkeypatch.setenv("RUN_STORE_BACKEND", "memory")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    from app.config import get_settings

    get_settings.cache_clear()
    from fastapi.testclient import TestClient

    from app.api.main import app

    yield TestClient(app)
    get_settings.cache_clear()


def test_preview_comms_default_renders_both(client):
    r = client.post("/v1/preview/comms", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["email"]["html"].lstrip().startswith("<!DOCTYPE")
    assert "Best regards" in body["email"]["html"]
    # Slack Block Kit: a header block first, plus the field grid + body.
    assert body["slack"]["blocks"][0]["type"] == "header"
    assert len(body["slack"]["blocks"]) >= 3


def test_preview_comms_applies_signature_overrides(client):
    r = client.post(
        "/v1/preview/comms",
        json={
            "signature_name": "Jane Doe",
            "signature_company": "Acme Corp",
            "disclose_ai_assistance": True,
            "body": "Dear Controller,\n\n- Variance 12%\n\nPlease approve.\n\nThanks,",
        },
    )
    assert r.status_code == 200
    html = r.json()["email"]["html"]
    assert "Jane Doe" in html
    assert "Acme Corp" in html
    assert "Prepared by AP Exception Agent" in html  # AI-disclosure footer on


def test_preview_comms_html_escapes_body(client):
    r = client.post(
        "/v1/preview/comms",
        json={"body": "Hi <script>alert('x')</script>\n\nReview please."},
    )
    html = r.json()["email"]["html"]
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_preview_applies_brand_color_and_logo(client):
    r = client.post(
        "/v1/preview/comms",
        json={"brand_color": "#aa00ff", "logo_url": "https://x.com/logo.png", "body": "Hello"},
    )
    html = r.json()["email"]["html"]
    assert "#aa00ff" in html          # brand color overrides the channel preset bar
    assert "logo.png" in html         # logo rendered in the header


def test_preview_draft_404_for_unknown_run(client):
    # No such run → tenant-ownership dependency returns 404.
    r = client.get("/v1/runs/run_nope/drafts/INV-1/preview")
    assert r.status_code == 404
