"""OAuth connect/callback for per-org Gmail + Slack (admin-only, Phase 2c).

Flow: the admin hits `…/connect` to get a provider consent URL (carrying a signed,
tenant-bound state), the browser is redirected to Google/Slack, the provider
redirects back to a frontend route which POSTs the `code` + `state` to `…/callback`.
The callback verifies the state, exchanges the code, and stores the resulting
credential (refresh token / bot token) encrypted via the email/slack integration.

Inert until the platform OAuth apps are registered (GOOGLE_OAUTH_* / SLACK_*).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from app.api import org_config
from app.api.auth import Principal
from app.api.deps import require_permission
from app.api.roles import CONFIG_WRITE
from app.comms import oauth
from app.config import get_settings
from app.security import crypto
from app.security.oauth_state import OAuthStateError, sign, verify

log = logging.getLogger("ap_agent.routes_oauth")

router = APIRouter(prefix="/v1/integrations", tags=["oauth"])


class OAuthCallback(BaseModel):
    code: str
    state: str


def _require_enc() -> None:
    if not crypto.is_configured():
        raise HTTPException(400, "CONFIG_ENC_KEY is not set — cannot store OAuth credentials.")


# --------------------------------------------------------------------------- #
# Google (Gmail send)
# --------------------------------------------------------------------------- #
@router.get("/google/connect")
def google_connect(principal: Principal = Depends(require_permission(CONFIG_WRITE))) -> dict:
    s = get_settings()
    if not oauth.google_configured(s):
        raise HTTPException(400, "Google OAuth is not configured on the server (GOOGLE_OAUTH_*).")
    _require_enc()
    state = sign({"t": principal.tenant_id, "k": org_config.EMAIL})
    return {"auth_url": oauth.google_auth_url(s, state)}


@router.post("/google/callback")
def google_callback(
    body: OAuthCallback = Body(...),
    principal: Principal = Depends(require_permission(CONFIG_WRITE)),
) -> dict:
    s = get_settings()
    _require_enc()
    try:
        st = verify(body.state)
    except OAuthStateError as e:
        raise HTTPException(400, f"invalid state: {e}") from e
    if st.get("t") != principal.tenant_id:
        raise HTTPException(403, "state does not match your organization")
    try:
        res = oauth.google_exchange_code(s, body.code)
    except oauth.OAuthError as e:
        raise HTTPException(502, str(e)) from e
    org_config.upsert(
        tenant_id=principal.tenant_id,
        kind=org_config.EMAIL,
        secret=res["refresh_token"],
        meta={"mode": "oauth", "from_address": res.get("email", "")},
        actor=principal.subject or "unknown",
    )
    log.info("oauth: gmail connected for tenant=%s by=%s", principal.tenant_id, principal.subject)
    return {"status": "ok", "email": res.get("email", "")}


# --------------------------------------------------------------------------- #
# Slack (chat:write)
# --------------------------------------------------------------------------- #
@router.get("/slack/connect")
def slack_connect(principal: Principal = Depends(require_permission(CONFIG_WRITE))) -> dict:
    s = get_settings()
    if not oauth.slack_configured(s):
        raise HTTPException(400, "Slack OAuth is not configured on the server (SLACK_CLIENT_*).")
    _require_enc()
    state = sign({"t": principal.tenant_id, "k": org_config.SLACK})
    return {"auth_url": oauth.slack_install_url(s, state)}


@router.post("/slack/callback")
def slack_callback(
    body: OAuthCallback = Body(...),
    principal: Principal = Depends(require_permission(CONFIG_WRITE)),
) -> dict:
    s = get_settings()
    _require_enc()
    try:
        st = verify(body.state)
    except OAuthStateError as e:
        raise HTTPException(400, f"invalid state: {e}") from e
    if st.get("t") != principal.tenant_id:
        raise HTTPException(403, "state does not match your organization")
    try:
        res = oauth.slack_exchange_code(s, body.code)
    except oauth.OAuthError as e:
        raise HTTPException(502, str(e)) from e
    org_config.upsert(
        tenant_id=principal.tenant_id,
        kind=org_config.SLACK,
        secret=res["bot_token"],
        meta={"mode": "oauth", "team": res.get("team", ""), "channel": res.get("channel", "")},
        actor=principal.subject or "unknown",
    )
    log.info("oauth: slack connected for tenant=%s by=%s", principal.tenant_id, principal.subject)
    return {"status": "ok", "team": res.get("team", "")}
