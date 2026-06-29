"""SQLAlchemy-backed run store (the recommended durable backend).

Persists each run as one `runs` row — the full serialized RunState in a JSON
column plus indexed scalar columns — using the same engine/DATABASE_URL as the
normalized analytical tables. One database, durable across restarts, no
Supabase REST/PostgREST/RLS layer.

Public interface mirrors the in-memory RunStore exactly:
    put / get / list_ids / patch_draft / update_draft_send_result
"""
from __future__ import annotations

import logging
from enum import Enum

from sqlalchemy import select, text

from app.api.run_serde import deserialize_state, serialize_state
from app.config import Settings
from app.db import models as m
from app.db.session import init_db, session_scope
from app.graph.state import RunState

log = logging.getLogger("ap_agent.store.db")


def _scalars(state: RunState) -> dict:
    """Indexed scalar columns (with real datetimes, unlike the JSON blob)."""
    status = state.get("status")
    return {
        "tenant_id": state.get("tenant_id"),
        "status": status.value if isinstance(status, Enum) else status,
        "current_node": state.get("current_node"),
        "created_at": state.get("created_at"),
        "completed_at": state.get("completed_at"),
        "rows_accepted": len(state.get("rows", [])),
        "rows_quarantined": len(state.get("quarantined", [])),
    }


class SqlAlchemyRunStore:
    """Durable run store backed by the `runs` table on DATABASE_URL."""

    backend_name = "db"

    def __init__(self, settings: Settings) -> None:
        # Ensure the schema exists (idempotent; create_all skips existing tables).
        init_db()
        log.info("SQLAlchemy run store initialized (%s)", settings.database_url.split("://", 1)[0])

    def ping(self) -> None:
        """Readiness probe — round-trips a trivial query to the DB."""
        with session_scope() as s:
            s.execute(text("SELECT 1"))

    def put(self, state: RunState) -> None:
        cols = _scalars(state)
        blob = serialize_state(state)
        with session_scope() as s:
            obj = s.get(m.Run, state["run_id"])
            if obj is None:
                s.add(m.Run(run_id=state["run_id"], state=blob, **cols))
            else:
                obj.state = blob
                for k, v in cols.items():
                    setattr(obj, k, v)

    def get(self, run_id: str) -> RunState | None:
        with session_scope() as s:
            obj = s.get(m.Run, run_id)
            if obj is None:
                return None
            return deserialize_state(obj.state)

    def list_ids(self) -> list[str]:
        with session_scope() as s:
            rows = s.execute(
                select(m.Run.run_id).order_by(m.Run.created_at.desc())
            ).all()
            return [r[0] for r in rows]

    def _mutate_draft(self, run_id: str, invoice_id: str, update: dict) -> bool:
        """Read-modify-write a single draft inside ONE transaction.

        Doing the load and the store in the same session_scope() (rather than
        get() then put(), each opening its own connection) closes the race where
        two concurrent edits to the same run clobber each other.
        """
        with session_scope() as s:
            obj = s.get(m.Run, run_id)
            if obj is None:
                return False
            state = deserialize_state(obj.state)
            drafts = state.get("drafts", [])
            for i, d in enumerate(drafts):
                if d.invoice_id == invoice_id:
                    drafts[i] = d.model_copy(update=update)
                    state["drafts"] = drafts
                    obj.state = serialize_state(state)
                    for k, v in _scalars(state).items():
                        setattr(obj, k, v)
                    return True
            return False

    def claim_draft_for_send(
        self, run_id: str, invoice_id: str, *, force: bool = False
    ) -> bool:
        """Atomically claim a draft for sending (status → SENDING).

        Locks the run row (SELECT ... FOR UPDATE) for the duration of the
        read-modify-write, so a concurrent claim on the same draft blocks until
        this transaction commits and then sees SENDING — preventing a
        double-send across processes/replicas. A stale SENDING claim (older than
        the TTL — a worker died mid-send) is reclaimable, so it self-heals.
        Returns True iff this caller won the claim. (FOR UPDATE is a no-op on
        SQLite, which serializes writes anyway.) ``force=True`` allows reclaiming
        an already SENT/DRYRUN draft for an explicit operator resend."""
        from datetime import UTC, datetime

        from app.config import get_settings
        from app.schemas import SendStatus, claimable_for_send

        now = datetime.now(UTC)
        ttl = get_settings().comms_send_claim_ttl_seconds
        with session_scope() as s:
            obj = s.execute(
                select(m.Run).where(m.Run.run_id == run_id).with_for_update()
            ).scalar_one_or_none()
            if obj is None:
                return False
            state = deserialize_state(obj.state)
            drafts = state.get("drafts", [])
            for i, d in enumerate(drafts):
                if d.invoice_id == invoice_id:
                    if not claimable_for_send(
                        d.send_status, d.send_claimed_at, now, ttl, force=force
                    ):
                        return False
                    drafts[i] = d.model_copy(
                        update={"send_status": SendStatus.SENDING, "send_claimed_at": now}
                    )
                    state["drafts"] = drafts
                    obj.state = serialize_state(state)
                    for k, v in _scalars(state).items():
                        setattr(obj, k, v)
                    return True
            return False

    def patch_draft(
        self,
        run_id: str,
        invoice_id: str,
        *,
        subject: str | None,
        body: str,
    ) -> bool:
        return self._mutate_draft(
            run_id,
            invoice_id,
            {"subject": subject, "body": body, "is_edited_by_human": True},
        )

    def update_draft_send_result(
        self,
        run_id: str,
        invoice_id: str,
        *,
        send_status,
        send_provider: str | None,
        send_message_id: str | None,
        recipient: str | None,
        sent_at,
        send_error: str | None = None,
    ) -> bool:
        return self._mutate_draft(
            run_id,
            invoice_id,
            {
                "send_status": send_status,
                "send_provider": send_provider,
                "send_message_id": send_message_id,
                "recipient": recipient,
                "sent_at": sent_at,
                "send_error": send_error,
            },
        )
