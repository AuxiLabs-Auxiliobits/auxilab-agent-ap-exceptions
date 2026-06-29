"""Engine + session factory for the normalized DB.

Sync SQLAlchemy (the pipeline runs in a thread-pool executor, and the read
routes are sync). One engine per process, created lazily so importing this
module never opens a connection.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.models import Base

log = logging.getLogger("ap_agent.db")

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None
_initialized = False


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        url = get_settings().database_url
        # SQLite needs check_same_thread off for the executor threads.
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, future=True, pool_pre_ping=True, connect_args=connect_args)
        if url.startswith("sqlite"):
            # SQLite ignores FK constraints unless explicitly enabled per-connection.
            @event.listens_for(_engine, "connect")
            def _fk_pragma(dbapi_conn, _record):  # noqa: ANN001
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.close()

        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
        log.info("DB engine created (%s)", url.split("://", 1)[0])
    return _engine


def init_db() -> None:
    """Create all tables if they don't exist (idempotent). Safe for dev/sqlite;
    for Postgres/Supabase prefer Alembic migrations in production."""
    global _initialized
    if _initialized:
        return
    Base.metadata.create_all(get_engine())
    _initialized = True
    log.info("DB schema ensured (create_all)")


def reset_engine() -> None:
    """Dispose and forget the cached engine/session factory.

    For tests that point DATABASE_URL at a fresh database between cases; not for
    production use."""
    global _engine, _SessionLocal, _initialized
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
    _initialized = False


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session: commit on success, rollback on error."""
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
