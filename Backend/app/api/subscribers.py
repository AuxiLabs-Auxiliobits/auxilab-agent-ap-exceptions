"""Newsletter subscriber storage (platform-level marketing list).

Reuses the normalized-DB session; ensures its table exists on first use so the
feature works on a fresh sqlite/dev DB regardless of DB_PERSISTENCE_ENABLED.
"""
from __future__ import annotations

import logging
import secrets

from app.config import get_settings

log = logging.getLogger("ap_agent.subscribers")

_table_ensured = False


def _ensure_table() -> None:
    global _table_ensured
    if _table_ensured:
        return
    from app.db.models import Subscriber
    from app.db.session import get_engine

    Subscriber.__table__.create(bind=get_engine(), checkfirst=True)
    _table_ensured = True


def add(email: str, *, source: str = "landing") -> tuple[str, bool]:
    """Add (or reactivate) a subscriber. Returns (unsubscribe_token, created)."""
    _ensure_table()
    from app.db.models import Subscriber
    from app.db.session import session_scope

    email = email.strip().lower()
    with session_scope() as s:
        existing = s.query(Subscriber).filter(Subscriber.email == email).one_or_none()
        if existing is not None:
            created = False
            if existing.status != "active":
                existing.status = "active"  # re-subscribed via the form = fresh consent
            if not existing.unsubscribe_token:
                existing.unsubscribe_token = secrets.token_urlsafe(24)
            return existing.unsubscribe_token, created
        token = secrets.token_urlsafe(24)
        s.add(Subscriber(email=email, status="active", source=source, unsubscribe_token=token))
        return token, True


def list_active() -> list[dict]:
    """All active subscribers as {email, unsubscribe_token}."""
    _ensure_table()
    from app.db.models import Subscriber
    from app.db.session import session_scope

    with session_scope() as s:
        rows = s.query(Subscriber).filter(Subscriber.status == "active").all()
        return [{"email": r.email, "unsubscribe_token": r.unsubscribe_token} for r in rows]


def counts() -> dict:
    _ensure_table()
    from app.db.models import Subscriber
    from app.db.session import session_scope

    with session_scope() as s:
        active = s.query(Subscriber).filter(Subscriber.status == "active").count()
        total = s.query(Subscriber).count()
        return {"active": active, "total": total, "unsubscribed": total - active}


def unsubscribe_by_token(token: str) -> str | None:
    """Mark unsubscribed. Returns the email if found, else None."""
    _ensure_table()
    from app.db.models import Subscriber
    from app.db.session import session_scope

    with session_scope() as s:
        row = s.query(Subscriber).filter(Subscriber.unsubscribe_token == token).one_or_none()
        if row is None:
            return None
        row.status = "unsubscribed"
        return row.email


def unsubscribe_url(token: str) -> str:
    return f"{get_settings().unsubscribe_base}/v1/unsubscribe?token={token}"
