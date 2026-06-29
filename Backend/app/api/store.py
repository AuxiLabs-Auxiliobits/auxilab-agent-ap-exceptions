"""Run store.

Three backends with an identical, intentionally narrow interface
(get/put/list/patch):
  - in-memory dict for dev/tests (this module),
  - SQLAlchemy/DATABASE_URL store (db_store.py) — the recommended durable
    backend; one Postgres for both the run store and the normalized tables,
  - Supabase REST store (supabase_store.py) — durable via the Supabase API.

`get_store()` picks one from RUN_STORE_BACKEND (default "auto").
"""
from __future__ import annotations

import logging
import threading
from copy import deepcopy

from app.config import get_settings
from app.graph.state import RunState

log = logging.getLogger("ap_agent.store")


class RunStore:
    backend_name = "memory"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._runs: dict[str, RunState] = {}

    def ping(self) -> None:
        """Readiness probe. In-memory store is always ready; durable backends
        override this to verify their connection (see /readyz)."""
        return None

    def put(self, state: RunState) -> None:
        with self._lock:
            self._runs[state["run_id"]] = deepcopy(state)

    def get(self, run_id: str) -> RunState | None:
        with self._lock:
            v = self._runs.get(run_id)
            return deepcopy(v) if v is not None else None

    def list_ids(self) -> list[str]:
        with self._lock:
            return list(self._runs.keys())

    def patch_draft(
        self,
        run_id: str,
        invoice_id: str,
        *,
        subject: str | None,
        body: str,
    ) -> bool:
        with self._lock:
            state = self._runs.get(run_id)
            if not state:
                return False
            for d in state.get("drafts", []):
                if d.invoice_id == invoice_id:
                    updated = d.model_copy(
                        update={
                            "subject": subject,
                            "body": body,
                            "is_edited_by_human": True,
                        }
                    )
                    # replace
                    state["drafts"] = [
                        updated if x.invoice_id == invoice_id else x
                        for x in state["drafts"]
                    ]
                    return True
            return False

    def claim_draft_for_send(
        self, run_id: str, invoice_id: str, *, force: bool = False
    ) -> bool:
        """Atomically claim a draft for sending (status → SENDING).

        Returns True if this caller won the claim (the draft was claimable or its
        prior SENDING claim went stale); False if the draft is missing or already
        terminal/recently-claimed. Atomic under the store lock, so two concurrent
        send requests for the same draft can't both proceed and double-send.
        ``force=True`` allows reclaiming an already SENT/DRYRUN draft for an
        explicit operator resend (still blocked while a send is in flight)."""
        from datetime import UTC, datetime

        from app.config import get_settings
        from app.schemas import SendStatus, claimable_for_send

        now = datetime.now(UTC)
        ttl = get_settings().comms_send_claim_ttl_seconds
        with self._lock:
            state = self._runs.get(run_id)
            if not state:
                return False
            for d in state.get("drafts", []):
                if d.invoice_id == invoice_id:
                    if not claimable_for_send(
                        d.send_status, d.send_claimed_at, now, ttl, force=force
                    ):
                        return False
                    updated = d.model_copy(
                        update={"send_status": SendStatus.SENDING, "send_claimed_at": now}
                    )
                    state["drafts"] = [
                        updated if x.invoice_id == invoice_id else x
                        for x in state["drafts"]
                    ]
                    return True
            return False

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
        """Persist the outcome of a send attempt onto the draft."""
        with self._lock:
            state = self._runs.get(run_id)
            if not state:
                return False
            for d in state.get("drafts", []):
                if d.invoice_id == invoice_id:
                    updated = d.model_copy(
                        update={
                            "send_status": send_status,
                            "send_provider": send_provider,
                            "send_message_id": send_message_id,
                            "recipient": recipient,
                            "sent_at": sent_at,
                            "send_error": send_error,
                        }
                    )
                    state["drafts"] = [
                        updated if x.invoice_id == invoice_id else x
                        for x in state["drafts"]
                    ]
                    return True
            return False


_store = None


def _resolve_backend(settings) -> str:
    """Map RUN_STORE_BACKEND (incl. "auto") to a concrete backend name."""
    choice = (settings.run_store_backend or "auto").strip().lower()
    if choice in ("db", "supabase", "memory"):
        return choice
    # auto: prefer the DATABASE_URL DB store when DB persistence is on; else
    # Supabase REST when configured; else in-memory.
    if settings.db_persistence_enabled:
        return "db"
    if settings.supabase_url and settings.supabase_key:
        return "supabase"
    return "memory"


def get_store():
    """Return the process-wide run store, selected by RUN_STORE_BACKEND.

    In dev, a durable backend that fails to initialize degrades to the
    in-memory store (logged loudly; runs will NOT survive restarts). In
    production/staging that silent data-loss is unacceptable, so a failed
    durable-store init is re-raised and the app refuses to serve — better a
    hard, visible failure than runs that quietly vanish on restart.
    """
    global _store
    if _store is not None:
        return _store

    settings = get_settings()
    backend = _resolve_backend(settings)

    def _fallback_or_raise(kind: str, exc: Exception):
        if settings.is_protected_env:
            raise RuntimeError(
                f"{kind} run store init failed in environment="
                f"{settings.environment!r}: {exc}. Refusing to start with a "
                "non-durable in-memory store (runs would be lost on restart). "
                "Fix the store configuration or set RUN_STORE_BACKEND=memory "
                "explicitly to accept ephemeral storage."
            ) from exc
        log.error(
            "%s run store init failed (%s) — falling back to in-memory store. "
            "Runs will NOT survive restarts.",
            kind,
            exc,
        )

    if backend == "db":
        try:
            from app.api.db_store import SqlAlchemyRunStore

            _store = SqlAlchemyRunStore(settings)
            return _store
        except Exception as e:  # noqa: BLE001 — controlled fallback/raise below
            _fallback_or_raise("DB", e)
    elif backend == "supabase":
        try:
            from app.api.supabase_store import SupabaseRunStore

            _store = SupabaseRunStore(settings)
            return _store
        except Exception as e:  # noqa: BLE001 — controlled fallback/raise below
            _fallback_or_raise("Supabase", e)

    _store = RunStore()
    return _store


def reset_store_cache() -> None:
    """Drop the process-wide store singleton (used by tests to re-select a
    backend after changing env vars)."""
    global _store
    _store = None
