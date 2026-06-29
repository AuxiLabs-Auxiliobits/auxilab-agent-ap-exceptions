"""Read-only configuration/status endpoint for the reviewer console.

Exposes the *non-secret* runtime configuration so the UI can show which AI
provider is active, whether outbound comms are in dry-run mode, and the
deterministic thresholds/weights in force. Secrets (API keys, SMTP password,
webhook URL) are NEVER returned — only booleans indicating whether a channel
is configured.

This endpoint is intentionally read-only. Configuration is sourced from
environment / .env and stays under change-control (see the rules-engine
auditability model); it is not mutable at runtime from the browser.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.auth import Principal, require_auth
from app.config import get_settings

router = APIRouter(prefix="/v1", tags=["config"])


@router.get("/me")
def get_me(principal: Principal = Depends(require_auth)) -> dict:
    """The authenticated caller's identity, role, and effective permissions.

    Authoritative source for the UI's RBAC gating — the browser checks
    ``permissions`` here rather than re-deriving the role → permission matrix,
    so backend and frontend can never drift. With auth disabled this returns the
    local ``dev``/``admin`` principal (every permission granted)."""
    return {
        "subject": principal.subject,
        "tenant_id": principal.tenant_id,
        "role": principal.role,
        "permissions": principal.permissions,
    }


@router.get("/config")
def get_config() -> dict:
    s = get_settings()
    return {
        "app_name": s.app_name,
        "environment": s.environment,
        "ai": {
            "active_provider": s.active_ai_provider,
            "classify_model": s.model_for("classify"),
            "draft_model": s.model_for("draft"),
            "mock_mode": s.active_ai_provider == "mock",
        },
        "comms": {
            # Safety-critical: is the system actually dispatching, or writing
            # dry-run artifacts?
            "dryrun": s.comms_dryrun,
            "email_configured": bool(s.gmail_smtp_user and s.gmail_smtp_password),
            "slack_configured": bool(s.slack_webhook_url),
            "html_enabled": s.comms_email_html_enabled,
            "per_domain_daily_cap": s.comms_per_domain_daily_cap,
        },
        "severity_thresholds": {
            "high_amount": float(s.severity_high_amount),
            "high_days": s.severity_high_days,
            "medium_amount_min": float(s.severity_medium_amount_min),
        },
        "priority": {
            "weights": {
                "amount": s.w_amount,
                "age": s.w_age,
                "severity": s.w_severity,
                "path": s.w_path,
                "confidence": s.w_conf,
            },
            "high_threshold": s.high_threshold,
            "medium_threshold": s.medium_threshold,
        },
    }
