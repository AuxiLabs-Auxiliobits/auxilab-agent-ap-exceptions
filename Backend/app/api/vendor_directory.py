"""Per-tenant vendor → email directory (F1-5).

A managed mapping of vendor name → AR email (+ contact), scoped to a tenant, so
a mixed-vendor upload routes each invoice to the right vendor. The recipient
resolver consults ``get_email`` (wrapped to never raise into a send); the API
(routes_vendor_contacts) drives ``upsert`` / ``list_contacts`` / ``delete``.

Like org_config, this self-creates its table as a safety net so the feature
works on a fresh dev/sqlite DB regardless of DB_PERSISTENCE_ENABLED.
"""
from __future__ import annotations

import logging

log = logging.getLogger("ap_agent.vendor_directory")

_table_ensured = False


def _norm(vendor_name: str | None) -> str:
    return (vendor_name or "").strip().lower()


def _ensure_table() -> None:
    global _table_ensured
    if _table_ensured:
        return
    from app.db.models import VendorContact
    from app.db.session import get_engine

    VendorContact.__table__.create(bind=get_engine(), checkfirst=True)
    _table_ensured = True


def get_email(tenant_id: str | None, vendor_name: str | None) -> str | None:
    """Resolve a vendor's email from the tenant's directory, or None.

    Best-effort: any DB error returns None so recipient resolution falls through
    rather than breaking a send."""
    key = _norm(vendor_name)
    if not tenant_id or not key:
        return None
    try:
        _ensure_table()
        from app.db.models import VendorContact
        from app.db.session import session_scope

        with session_scope() as s:
            row = (
                s.query(VendorContact)
                .filter(VendorContact.tenant_id == tenant_id, VendorContact.vendor_key == key)
                .one_or_none()
            )
            return row.email if row is not None else None
    except Exception:  # noqa: BLE001 — a directory miss must never break a send
        log.warning(
            "vendor_directory: lookup failed (tenant=%s vendor=%r)", tenant_id, vendor_name,
            exc_info=True,
        )
        return None


def upsert(
    *, tenant_id: str, vendor_name: str, email: str, contact_name: str | None = None,
    actor: str | None = None,
) -> None:
    """Create or update a tenant's vendor contact (keyed on normalized name)."""
    _ensure_table()
    from app.db.models import VendorContact
    from app.db.session import session_scope

    key = _norm(vendor_name)
    with session_scope() as s:
        existing = (
            s.query(VendorContact)
            .filter(VendorContact.tenant_id == tenant_id, VendorContact.vendor_key == key)
            .one_or_none()
        )
        if existing is None:
            s.add(
                VendorContact(
                    tenant_id=tenant_id, vendor_key=key, vendor_name=vendor_name.strip(),
                    email=email.strip(), contact_name=(contact_name or None), updated_by=actor,
                )
            )
        else:
            existing.vendor_name = vendor_name.strip()
            existing.email = email.strip()
            existing.contact_name = contact_name or None
            existing.updated_by = actor


def list_contacts(tenant_id: str) -> list[dict]:
    """All vendor contacts for a tenant (alphabetical by vendor name)."""
    _ensure_table()
    from app.db.models import VendorContact
    from app.db.session import session_scope

    with session_scope() as s:
        rows = (
            s.query(VendorContact)
            .filter(VendorContact.tenant_id == tenant_id)
            .order_by(VendorContact.vendor_name)
            .all()
        )
        return [
            {
                "vendor_name": r.vendor_name,
                "email": r.email,
                "contact_name": r.contact_name,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                "updated_by": r.updated_by,
            }
            for r in rows
        ]


def delete(tenant_id: str, vendor_name: str) -> bool:
    """Remove a tenant's vendor contact. Returns True if a row was deleted."""
    _ensure_table()
    from app.db.models import VendorContact
    from app.db.session import session_scope

    key = _norm(vendor_name)
    with session_scope() as s:
        existing = (
            s.query(VendorContact)
            .filter(VendorContact.tenant_id == tenant_id, VendorContact.vendor_key == key)
            .one_or_none()
        )
        if existing is None:
            return False
        s.delete(existing)
        return True
