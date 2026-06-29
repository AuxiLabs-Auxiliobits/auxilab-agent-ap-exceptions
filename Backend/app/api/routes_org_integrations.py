"""Per-org integration settings — admin-only, BYOK (Phase 2a).

An org admin configures that org's own AI provider credentials here. Secrets are
encrypted at rest and **never** returned: GET reports only `configured` + non-secret
metadata. Every endpoint is gated on the admin-only `config:write` permission and
scoped to the caller's tenant.

  GET    /v1/org/integrations            list status for the caller's org
  PUT    /v1/org/integrations/{kind}     set/replace a provider's key + meta
  DELETE /v1/org/integrations/{kind}     remove a provider's config
  POST   /v1/org/integrations/{kind}/test   resolve + report effective provider

Email/Slack (OAuth/ESP) land in Phase 2c; only AI kinds are writable here.
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
from app.security import crypto

log = logging.getLogger("ap_agent.routes_integrations")

router = APIRouter(prefix="/v1/org/integrations", tags=["integrations"])


class IntegrationInput(BaseModel):
    """Write payload. `secret` is the provider key/password/webhook (optional on a
    meta-only update, where an existing secret is kept). Other fields are non-secret
    metadata; only the ones relevant to the kind are stored."""

    secret: str | None = None
    # AI (anthropic/gemini): model ids.
    classify_model: str | None = None
    draft_model: str | None = None
    # Azure.
    endpoint: str | None = None
    deployment: str | None = None
    api_version: str | None = None
    # Email (SMTP). `secret` is the SMTP password.
    smtp_host: str | None = None
    smtp_port: str | None = None
    from_address: str | None = None
    dryrun: bool | None = None
    # Branding (no secret).
    signature_name: str | None = None
    signature_team: str | None = None
    signature_company: str | None = None
    signature_disclaimer: str | None = None
    disclose_ai: bool | None = None
    brand_color: str | None = None
    logo_url: str | None = None


def _meta_from(kind: str, body: IntegrationInput) -> dict:
    extra: dict = {}
    if kind == org_config.AI_AZURE:
        meta = {"endpoint": body.endpoint, "deployment": body.deployment, "api_version": body.api_version}
    elif kind in (org_config.AI_ANTHROPIC, org_config.AI_GEMINI):
        meta = {"classify_model": body.classify_model, "draft_model": body.draft_model}
    elif kind == org_config.EMAIL:
        meta = {"smtp_host": body.smtp_host, "smtp_port": body.smtp_port, "from_address": body.from_address}
        if body.dryrun is not None:
            extra["dryrun"] = body.dryrun
    elif kind == org_config.BRANDING:
        meta = {
            "signature_name": body.signature_name,
            "signature_team": body.signature_team,
            "signature_company": body.signature_company,
            "signature_disclaimer": body.signature_disclaimer,
            "brand_color": body.brand_color,
            "logo_url": body.logo_url,
        }
        if body.disclose_ai is not None:
            extra["disclose_ai"] = body.disclose_ai
    else:  # slack — the webhook URL is the secret; no meta
        meta = {}
    # Drop empty strings/None, but keep explicit booleans (e.g. dryrun=false).
    cleaned = {k: v for k, v in meta.items() if v not in (None, "")}
    cleaned.update(extra)
    return cleaned


@router.get("")
def list_integrations(principal: Principal = Depends(require_permission(CONFIG_WRITE))) -> dict:
    """Status for every configured integration in the caller's org (no secrets)."""
    from app.config import get_settings

    s = get_settings()
    return {
        "tenant_id": principal.tenant_id,
        "per_org_config_enabled": s.per_org_config_enabled,
        "enc_key_configured": crypto.is_configured(),
        # Whether the *platform* has registered an OAuth app for each provider.
        # The UI uses these to enable/disable the "Connect via OAuth" buttons —
        # without them a connect attempt would just 400.
        "google_oauth_configured": oauth.google_configured(s),
        "slack_oauth_configured": oauth.slack_configured(s),
        "writable_kinds": list(org_config.WRITABLE_KINDS),
        "integrations": org_config.list_status(principal.tenant_id),
    }


@router.put("/{kind}")
def put_integration(
    kind: str,
    body: IntegrationInput = Body(...),
    principal: Principal = Depends(require_permission(CONFIG_WRITE)),
) -> dict:
    """Set/replace a provider's credentials. Encrypts the secret; never echoes it."""
    if kind not in org_config.WRITABLE_KINDS:
        raise HTTPException(
            400,
            f"unknown or non-writable integration '{kind}'. "
            f"Writable: {', '.join(org_config.WRITABLE_KINDS)}",
        )
    is_secret_kind = kind in org_config.SECRET_KINDS
    # Storing a secret needs the encryption key; branding (no secret) doesn't.
    if is_secret_kind and not crypto.is_configured():
        raise HTTPException(
            400,
            "CONFIG_ENC_KEY is not set on the server — secrets cannot be stored "
            "securely. Set it before configuring this provider.",
        )
    # A first-time secret-kind config needs a secret; a meta-only update may omit it.
    if is_secret_kind and not body.secret and not org_config.has_secret(principal.tenant_id, kind):
        raise HTTPException(422, "secret (API key / password / webhook URL) is required")

    try:
        org_config.upsert(
            tenant_id=principal.tenant_id,
            kind=kind,
            secret=body.secret,
            meta=_meta_from(kind, body),
            actor=principal.subject or "unknown",
        )
    except crypto.SecretCryptoError as e:
        raise HTTPException(400, str(e)) from e

    log.info(
        "integrations: %s set for tenant=%s by=%s",
        kind, principal.tenant_id, principal.subject,
    )
    return {"tenant_id": principal.tenant_id, "integrations": org_config.list_status(principal.tenant_id)}


@router.delete("/{kind}")
def delete_integration(
    kind: str,
    principal: Principal = Depends(require_permission(CONFIG_WRITE)),
) -> dict:
    """Remove a provider's config for the caller's org."""
    removed = org_config.delete(principal.tenant_id, kind)
    if not removed:
        raise HTTPException(404, f"no '{kind}' integration configured")
    return {"tenant_id": principal.tenant_id, "removed": kind}


@router.post("/{kind}/test")
def test_integration(
    kind: str,
    principal: Principal = Depends(require_permission(CONFIG_WRITE)),
) -> dict:
    """Resolve the org's stored config and report whether it's usable.

    Validates wiring (secret present, decryptable, provider selected) without a
    live provider call. Branding has nothing to test.
    """
    if kind == org_config.BRANDING:
        raise HTTPException(400, "branding has no connection to test")
    if kind not in org_config.WRITABLE_KINDS:
        raise HTTPException(400, f"unknown integration '{kind}'")
    try:
        eff = org_config.resolve_settings(principal.tenant_id, force=True)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"could not resolve config: {e}") from e

    if kind in org_config.AI_KINDS:
        provider = eff.active_ai_provider
        ok = provider != "mock"
        return {
            "kind": kind, "ok": ok, "active_provider": provider,
            "classify_model": eff.model_for("classify"), "draft_model": eff.model_for("draft"),
            "detail": (
                f"Resolved provider '{provider}'." if ok
                else "No usable key resolved — falls back to mock. Check the key and that "
                "this is the highest-precedence configured provider."
            ),
        }
    if kind == org_config.EMAIL:
        ok = bool(eff.gmail_smtp_user and eff.gmail_smtp_password)
        return {
            "kind": kind, "ok": ok,
            "detail": (
                f"SMTP ready — sending as {eff.gmail_smtp_user} via {eff.gmail_smtp_host}."
                if ok else "Incomplete — need a from address and SMTP password."
            ),
        }
    # slack
    ok = bool(eff.slack_webhook_url)
    return {
        "kind": kind, "ok": ok,
        "detail": "Slack webhook configured." if ok else "No Slack webhook URL resolved.",
    }
