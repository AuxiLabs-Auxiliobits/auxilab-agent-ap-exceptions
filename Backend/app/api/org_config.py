"""Per-org integration config: storage access + effective-settings resolution.

Phase 2a (BYOK): an organization's stored AI provider key/model overrides the
env defaults at run time, resolved per run from the caller's tenant. Secrets are
encrypted at rest (app.security.crypto) and never returned to clients.

`resolve_settings(tenant_id)` is the single entry point used by the run executor.
When PER_ORG_CONFIG_ENABLED is off (default) it returns the env `Settings`
unchanged, so behaviour and tests are unaffected.
"""
from __future__ import annotations

import logging
from typing import Any

from app.config import Settings, get_settings
from app.security import crypto

log = logging.getLogger("ap_agent.org_config")

# ---- integration "kind" constants ----
AI_ANTHROPIC = "ai_anthropic"
AI_GEMINI = "ai_gemini"
AI_AZURE = "ai_azure"
AI_KINDS: tuple[str, ...] = (AI_ANTHROPIC, AI_GEMINI, AI_AZURE)
EMAIL = "email"        # SMTP credentials (2c)
SLACK = "slack"        # incoming webhook (2c)
BRANDING = "branding"  # signature / tone — non-secret (2b)

# Kinds whose config includes an encrypted secret (require one on first save).
SECRET_KINDS: tuple[str, ...] = (*AI_KINDS, EMAIL, SLACK)
# Everything an admin can configure from the UI.
WRITABLE_KINDS: tuple[str, ...] = (*AI_KINDS, EMAIL, SLACK, BRANDING)


# --------------------------------------------------------------------------- #
# Storage access (SQLAlchemy, reusing the normalized-DB session).             #
# --------------------------------------------------------------------------- #
_table_ensured = False


def _ensure_table() -> None:
    """Create the org_integrations table if missing (idempotent).

    Production uses Alembic (`upgrade head` includes this table); this is a
    safety net so the feature works on a fresh sqlite/dev DB regardless of
    DB_PERSISTENCE_ENABLED."""
    global _table_ensured
    if _table_ensured:
        return
    from app.db.models import OrgIntegration
    from app.db.session import get_engine

    OrgIntegration.__table__.create(bind=get_engine(), checkfirst=True)
    _table_ensured = True


def _rows_for(tenant_id: str) -> list[dict]:
    """Load this tenant's integration rows as plain dicts (session detached)."""
    _ensure_table()
    from app.db.models import OrgIntegration
    from app.db.session import session_scope

    with session_scope() as s:
        rows = s.query(OrgIntegration).filter(OrgIntegration.tenant_id == tenant_id).all()
        return [
            {
                "kind": r.kind,
                "meta": dict(r.meta or {}),
                "configured": bool(r.configured),
                "secret": r.secret_ciphertext,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                "updated_by": r.updated_by,
            }
            for r in rows
        ]


def list_status(tenant_id: str) -> list[dict]:
    """Non-secret status for the UI — never includes the secret itself."""
    out = []
    for row in _rows_for(tenant_id):
        out.append(
            {
                "kind": row["kind"],
                "configured": row["configured"],
                "meta": row["meta"],
                "updated_at": row["updated_at"],
                "updated_by": row["updated_by"],
            }
        )
    return out


def has_secret(tenant_id: str, kind: str) -> bool:
    """True if an integration row with a stored secret exists for this kind."""
    return any(r["kind"] == kind and r["secret"] for r in _rows_for(tenant_id))


def upsert(
    *,
    tenant_id: str,
    kind: str,
    secret: str | None,
    meta: dict[str, Any],
    actor: str,
) -> None:
    """Create/replace an integration. Encrypts the secret; sets configured."""
    _ensure_table()
    from app.db.models import OrgIntegration
    from app.db.session import session_scope

    ciphertext = crypto.encrypt(secret) if secret else None
    with session_scope() as s:
        existing = (
            s.query(OrgIntegration)
            .filter(OrgIntegration.tenant_id == tenant_id, OrgIntegration.kind == kind)
            .one_or_none()
        )
        if existing is None:
            s.add(
                OrgIntegration(
                    tenant_id=tenant_id,
                    kind=kind,
                    secret_ciphertext=ciphertext,
                    meta=meta,
                    # Configured if there's a secret (AI/email/slack) OR meta
                    # (branding, which has no secret).
                    configured=ciphertext is not None or bool(meta),
                    created_by=actor,
                    updated_by=actor,
                )
            )
        else:
            # Keep the existing secret if none supplied (meta-only update).
            if ciphertext is not None:
                existing.secret_ciphertext = ciphertext
            existing.meta = meta
            existing.configured = existing.secret_ciphertext is not None or bool(meta)
            existing.updated_by = actor


def delete(tenant_id: str, kind: str) -> bool:
    """Remove an integration. Returns True if a row was deleted."""
    _ensure_table()
    from app.db.models import OrgIntegration
    from app.db.session import session_scope

    with session_scope() as s:
        existing = (
            s.query(OrgIntegration)
            .filter(OrgIntegration.tenant_id == tenant_id, OrgIntegration.kind == kind)
            .one_or_none()
        )
        if existing is None:
            return False
        s.delete(existing)
        return True


# --------------------------------------------------------------------------- #
# Effective-settings resolution (the per-run entry point).                    #
# --------------------------------------------------------------------------- #
def _decrypt_or_none(row: dict, tenant_id: str) -> str | None:
    if not row.get("secret"):
        return None
    try:
        return crypto.decrypt(row["secret"])
    except Exception:  # noqa: BLE001
        log.warning(
            "org_config: could not decrypt %s secret for tenant=%s; skipping it",
            row.get("kind"), tenant_id, exc_info=True,
        )
        return None


def _configured(rows: list[dict], *kinds: str) -> dict[str, dict]:
    return {r["kind"]: r for r in rows if r["configured"] and r["kind"] in kinds}


def _bool(value: Any) -> bool:
    return str(value).strip().lower() in ("true", "1", "yes")


def _apply_ai(updates: dict, rows: list[dict], tenant_id: str) -> None:
    by = _configured(rows, *AI_KINDS)
    chosen = next((by[k] for k in AI_KINDS if k in by), None)  # anthropic > gemini > azure
    if chosen is None:
        return
    secret = _decrypt_or_none(chosen, tenant_id)
    if not secret:
        return
    meta = chosen["meta"]
    # Clear all providers, then set the org's chosen one so env precedence resolves to it.
    updates.update({"anthropic_api_key": "", "gemini_api_key": "", "azure_openai_api_key": ""})
    if chosen["kind"] == AI_ANTHROPIC:
        updates["anthropic_api_key"] = secret
        if meta.get("classify_model"):
            updates["classify_model"] = meta["classify_model"]
        if meta.get("draft_model"):
            updates["draft_model"] = meta["draft_model"]
    elif chosen["kind"] == AI_GEMINI:
        updates["gemini_api_key"] = secret
        if meta.get("classify_model"):
            updates["gemini_classify_model"] = meta["classify_model"]
        if meta.get("draft_model"):
            updates["gemini_draft_model"] = meta["draft_model"]
    elif chosen["kind"] == AI_AZURE:
        updates["azure_openai_api_key"] = secret
        if meta.get("endpoint"):
            updates["azure_chat_openai_endpoint"] = meta["endpoint"]
        if meta.get("deployment"):
            updates["azure_openai_deployment"] = meta["deployment"]
        if meta.get("api_version"):
            updates["azure_openai_version"] = meta["api_version"]


def _apply_email(updates: dict, rows: list[dict], tenant_id: str) -> None:
    row = _configured(rows, EMAIL).get(EMAIL)
    if row is None:
        return
    meta = row["meta"]
    secret = _decrypt_or_none(row, tenant_id)  # SMTP password OR OAuth refresh token
    if meta.get("from_address"):
        updates["gmail_smtp_user"] = meta["from_address"]
    if "dryrun" in meta:
        updates["comms_dryrun"] = _bool(meta["dryrun"])
    if meta.get("mode") == "oauth":
        # Gmail API (OAuth) — the dispatcher prefers this over SMTP when present.
        if secret:
            updates["gmail_oauth_refresh_token"] = secret
        return
    # SMTP mode (default)
    if secret:
        updates["gmail_smtp_password"] = secret
    if meta.get("smtp_host"):
        updates["gmail_smtp_host"] = meta["smtp_host"]
    if meta.get("smtp_port"):
        try:
            updates["gmail_smtp_port"] = int(meta["smtp_port"])
        except (TypeError, ValueError):
            pass


def _apply_slack(updates: dict, rows: list[dict], tenant_id: str) -> None:
    row = _configured(rows, SLACK).get(SLACK)
    if row is None:
        return
    meta = row["meta"]
    secret = _decrypt_or_none(row, tenant_id)  # webhook URL OR OAuth bot token
    if meta.get("mode") == "oauth":
        if secret:
            updates["slack_bot_token"] = secret
        if meta.get("channel"):
            updates["slack_channel"] = meta["channel"]
        return
    # webhook mode (default)
    if secret:
        updates["slack_webhook_url"] = secret


def _apply_branding(updates: dict, rows: list[dict]) -> None:
    row = _configured(rows, BRANDING).get(BRANDING)
    if row is None:
        return
    meta = row["meta"]
    mapping = {
        "signature_name": "comms_signature_name",
        "signature_team": "comms_signature_team",
        "signature_company": "comms_signature_company",
        "signature_disclaimer": "comms_signature_disclaimer",
        "brand_color": "comms_brand_color",
        "logo_url": "comms_logo_url",
    }
    for src, dst in mapping.items():
        if meta.get(src):
            updates[dst] = meta[src]
    if "disclose_ai" in meta:
        updates["comms_disclose_ai_assistance"] = _bool(meta["disclose_ai"])


def resolve_settings(tenant_id: str, *, force: bool = False) -> Settings:
    """Return the effective Settings for a run/send in ``tenant_id``.

    Env `Settings` is the base; when PER_ORG_CONFIG_ENABLED is on (or ``force``,
    used by the integrations "test" endpoint) the org's configured AI provider
    (2a), email + Slack credentials (2c), and branding (2b) are layered on top.
    Falls back to env on any error — a misconfigured org never breaks the pipeline.
    """
    base = get_settings()
    if not tenant_id:
        return base
    # Normal runs: only apply overrides when the feature is on and this isn't the
    # dev/no-auth "default" tenant. `force` (the test endpoint) bypasses both so an
    # admin can validate stored config regardless of the flag or single-tenant id.
    if not force and (not base.per_org_config_enabled or tenant_id == "default"):
        return base
    try:
        rows = _rows_for(tenant_id)
    except Exception:  # noqa: BLE001 — config resolution must never break a run
        log.warning(
            "org_config: failed to load overrides for tenant=%s; using env defaults",
            tenant_id, exc_info=True,
        )
        return base

    updates: dict[str, Any] = {}
    _apply_ai(updates, rows, tenant_id)
    _apply_email(updates, rows, tenant_id)
    _apply_slack(updates, rows, tenant_id)
    _apply_branding(updates, rows)
    return base.model_copy(update=updates) if updates else base
