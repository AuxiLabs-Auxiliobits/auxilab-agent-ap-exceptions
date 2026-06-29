"""Sales/support lead storage (platform-level, captured from the public Contact form).

Persists every contact submission so a prospect is never lost if the
notification email is missed. Mirrors ``subscribers`` — ensures its table exists
on first use so the feature works on a fresh sqlite/dev DB regardless of
``DB_PERSISTENCE_ENABLED``.
"""
from __future__ import annotations

import logging

log = logging.getLogger("ap_agent.leads")

_table_ensured = False

# Map a Contact-form subject to a coarse intent tag for triage (sales vs support).
_INTENT_BY_SUBJECT: dict[str, str] = {
    "book a demo": "demo",
    "pricing & plans": "pricing",
    "pricing and plans": "pricing",
    "technical support": "support",
    "general enquiry": "general",
}


def intent_for(subject: str) -> str:
    """Coarse intent for a Contact-form subject; unknown subjects → 'general'."""
    return _INTENT_BY_SUBJECT.get((subject or "").strip().lower(), "general")


def _ensure_table() -> None:
    global _table_ensured
    if _table_ensured:
        return
    from app.db.models import Lead
    from app.db.session import get_engine

    Lead.__table__.create(bind=get_engine(), checkfirst=True)
    _table_ensured = True


def add(*, name: str, email: str, subject: str, message: str) -> tuple[str, str]:
    """Persist a lead. Returns (lead_id, intent)."""
    _ensure_table()
    from app.db.models import Lead
    from app.db.session import session_scope

    intent = intent_for(subject)
    with session_scope() as s:
        lead = Lead(
            name=(name or "").strip() or None,
            email=(email or "").strip().lower(),
            intent=intent,
            subject=(subject or "").strip() or None,
            message=(message or "").strip(),
        )
        s.add(lead)
        s.flush()  # populate the server/Python default id before the session closes
        return str(lead.id), intent


def list_recent(limit: int = 100) -> list[dict]:
    """Newest-first leads for the operator console (token-gated route)."""
    _ensure_table()
    from app.db.models import Lead
    from app.db.session import session_scope

    capped = max(1, min(limit, 1000))
    with session_scope() as s:
        rows = s.query(Lead).order_by(Lead.created_at.desc()).limit(capped).all()
        return [
            {
                "id": str(r.id),
                "name": r.name,
                "email": r.email,
                "intent": r.intent,
                "subject": r.subject,
                "message": r.message,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


def counts() -> dict:
    """Total leads + a breakdown by intent."""
    _ensure_table()
    from sqlalchemy import func as safunc

    from app.db.models import Lead
    from app.db.session import session_scope

    with session_scope() as s:
        total = s.query(Lead).count()
        by_intent = dict(
            s.query(Lead.intent, safunc.count(Lead.id)).group_by(Lead.intent).all()
        )
        return {"total": total, "by_intent": by_intent}
