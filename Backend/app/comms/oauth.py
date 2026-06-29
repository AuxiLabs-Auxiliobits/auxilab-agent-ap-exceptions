"""OAuth flows for per-org Gmail (send) and Slack (chat:write) — httpx only.

These build the provider consent URLs and exchange the returned `code` for
long-lived credentials (Gmail refresh token / Slack bot token). The credentials
are then stored encrypted via app.api.org_config. Sending lives in
app.comms.providers.gmail_oauth (email) and slack_post() here (Slack).

No Google/Slack SDKs — just documented REST endpoints over httpx, so there are
no extra dependencies. Inert until the platform OAuth apps are registered and
GOOGLE_OAUTH_* / SLACK_* env vars are set.
"""
from __future__ import annotations

import logging
import urllib.parse
from typing import Any

import httpx

from app.config import Settings

log = logging.getLogger("ap_agent.comms.oauth")

# --- Google -------------------------------------------------------------- #
_GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"  # noqa: S105 — public endpoint URL
_GOOGLE_USERINFO = "https://www.googleapis.com/oauth2/v2/userinfo"
_GOOGLE_SCOPES = "openid email https://www.googleapis.com/auth/gmail.send"

# --- Slack --------------------------------------------------------------- #
_SLACK_AUTH = "https://slack.com/oauth/v2/authorize"
_SLACK_TOKEN = "https://slack.com/api/oauth.v2.access"  # noqa: S105 — public endpoint URL
_SLACK_SCOPES = "chat:write"


class OAuthError(RuntimeError):
    """OAuth misconfiguration or token-exchange failure."""


# --------------------------------------------------------------------------- #
# Google
# --------------------------------------------------------------------------- #
def google_configured(s: Settings) -> bool:
    return bool(s.google_oauth_client_id and s.google_oauth_client_secret and s.google_oauth_redirect_uri)


def google_auth_url(s: Settings, state: str) -> str:
    params = {
        "client_id": s.google_oauth_client_id,
        "redirect_uri": s.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": _GOOGLE_SCOPES,
        "access_type": "offline",      # request a refresh token
        "prompt": "consent",           # force refresh-token issuance every time
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{_GOOGLE_AUTH}?{urllib.parse.urlencode(params)}"


def google_exchange_code(s: Settings, code: str) -> dict[str, Any]:
    """Exchange an auth code for a refresh token + the authorized email."""
    resp = httpx.post(
        _GOOGLE_TOKEN,
        data={
            "code": code,
            "client_id": s.google_oauth_client_id,
            "client_secret": s.google_oauth_client_secret,
            "redirect_uri": s.google_oauth_redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=20.0,
    )
    if resp.status_code >= 300:
        raise OAuthError(f"Google token exchange failed: {resp.status_code} {resp.text[:200]}")
    tok = resp.json()
    refresh_token = tok.get("refresh_token")
    if not refresh_token:
        raise OAuthError("Google did not return a refresh_token (re-consent with prompt=consent).")
    email = ""
    access_token = tok.get("access_token")
    if access_token:
        try:
            info = httpx.get(
                _GOOGLE_USERINFO,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=15.0,
            )
            if info.status_code < 300:
                email = info.json().get("email", "")
        except httpx.HTTPError:
            log.warning("google: userinfo lookup failed; storing without from-address")
    return {"refresh_token": refresh_token, "email": email}


def google_access_token(s: Settings, refresh_token: str) -> str:
    """Mint a short-lived access token from a stored refresh token."""
    resp = httpx.post(
        _GOOGLE_TOKEN,
        data={
            "client_id": s.google_oauth_client_id,
            "client_secret": s.google_oauth_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=20.0,
    )
    if resp.status_code >= 300:
        raise OAuthError(f"Google token refresh failed: {resp.status_code} {resp.text[:200]}")
    token = resp.json().get("access_token")
    if not token:
        raise OAuthError("Google token refresh returned no access_token")
    return token


# --------------------------------------------------------------------------- #
# Slack
# --------------------------------------------------------------------------- #
def slack_configured(s: Settings) -> bool:
    return bool(s.slack_client_id and s.slack_client_secret and s.slack_redirect_uri)


def slack_install_url(s: Settings, state: str) -> str:
    params = {
        "client_id": s.slack_client_id,
        "scope": _SLACK_SCOPES,
        "redirect_uri": s.slack_redirect_uri,
        "state": state,
    }
    return f"{_SLACK_AUTH}?{urllib.parse.urlencode(params)}"


def slack_exchange_code(s: Settings, code: str) -> dict[str, Any]:
    """Exchange an install code for a bot token + workspace/channel info."""
    resp = httpx.post(
        _SLACK_TOKEN,
        data={
            "code": code,
            "client_id": s.slack_client_id,
            "client_secret": s.slack_client_secret,
            "redirect_uri": s.slack_redirect_uri,
        },
        timeout=20.0,
    )
    data = resp.json() if resp.status_code < 300 else {}
    if not data.get("ok"):
        raise OAuthError(f"Slack OAuth failed: {data.get('error') or resp.text[:200]}")
    return {
        "bot_token": data.get("access_token", ""),
        "team": (data.get("team") or {}).get("name", ""),
        "channel": (data.get("incoming_webhook") or {}).get("channel_id", ""),
    }


def slack_post(token: str, channel: str, text: str, blocks: list[dict] | None = None) -> str:
    """Post a message via chat.postMessage. Returns the message ts."""
    payload: dict[str, Any] = {"channel": channel, "text": text}
    if blocks:
        payload["blocks"] = blocks
    resp = httpx.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=15.0,
    )
    data = resp.json() if resp.status_code < 300 else {}
    if not data.get("ok"):
        raise OAuthError(f"Slack chat.postMessage failed: {data.get('error') or resp.text[:200]}")
    return data.get("ts", "")
