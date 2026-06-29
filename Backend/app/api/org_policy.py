"""Per-tenant resolution rulebook storage + resolution.

Each org may customize its rules policy; the route node resolves this (falling
back to the global default policy on disk). The full *validated* policy document
is stored, so an unsafe policy (missing catch-all, bad predicate) can never be
persisted. Mirrors ``leads``/``subscribers`` — ensures its table on first use so
it works on a fresh sqlite/dev DB regardless of ``DB_PERSISTENCE_ENABLED``.
"""
from __future__ import annotations

import logging
from typing import Any

from app.rules.engine import Policy, validate_policy

log = logging.getLogger("ap_agent.org_policy")

_table_ensured = False


def _ensure_table() -> None:
    global _table_ensured
    if _table_ensured:
        return
    from app.db.models import OrgPolicy
    from app.db.session import get_engine

    OrgPolicy.__table__.create(bind=get_engine(), checkfirst=True)
    _table_ensured = True


def get_policy(tenant_id: str) -> Policy | None:
    """The tenant's custom policy (validated), or None when it uses the default.

    A stored-but-invalid policy (shouldn't happen — we validate on write) is
    treated as None so routing always falls back safely rather than breaking."""
    if not tenant_id:
        return None
    _ensure_table()
    from app.db.models import OrgPolicy
    from app.db.session import session_scope

    with session_scope() as s:
        row = s.query(OrgPolicy).filter(OrgPolicy.tenant_id == tenant_id).one_or_none()
        if row is None or not row.policy:
            return None
        doc = dict(row.policy)
    try:
        return validate_policy(doc)
    except Exception:  # noqa: BLE001 — a corrupt stored policy must not break routing
        log.warning(
            "org_policy: stored policy for tenant=%s is invalid; using default",
            tenant_id, exc_info=True,
        )
        return None


def get_raw(tenant_id: str) -> dict | None:
    """The stored policy document as-is (for the editor), or None if not customized."""
    if not tenant_id:
        return None
    _ensure_table()
    from app.db.models import OrgPolicy
    from app.db.session import session_scope

    with session_scope() as s:
        row = s.query(OrgPolicy).filter(OrgPolicy.tenant_id == tenant_id).one_or_none()
        return dict(row.policy) if row and row.policy else None


def upsert(tenant_id: str, raw: Any, *, actor: str) -> Policy:
    """Validate then store a tenant's policy. Raises ValidationError/ValueError on
    bad input (the caller maps that to a 422) — nothing invalid is ever stored."""
    policy = validate_policy(raw)  # structure + catch-all safety invariant
    _ensure_table()
    from app.db.models import OrgPolicy
    from app.db.session import session_scope

    doc = policy.model_dump(mode="json")
    with session_scope() as s:
        row = s.query(OrgPolicy).filter(OrgPolicy.tenant_id == tenant_id).one_or_none()
        if row is None:
            s.add(OrgPolicy(tenant_id=tenant_id, version=policy.version, policy=doc, updated_by=actor))
        else:
            row.version = policy.version
            row.policy = doc
            row.updated_by = actor
    return policy


def delete(tenant_id: str) -> bool:
    """Remove a tenant's custom policy (revert to the global default). True if removed."""
    _ensure_table()
    from app.db.models import OrgPolicy
    from app.db.session import session_scope

    with session_scope() as s:
        row = s.query(OrgPolicy).filter(OrgPolicy.tenant_id == tenant_id).one_or_none()
        if row is None:
            return False
        s.delete(row)
        return True
