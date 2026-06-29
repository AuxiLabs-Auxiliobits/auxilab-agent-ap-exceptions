"""Supabase-backed run store.

Persists each run as one row in a `runs` table: indexed scalar columns for
listing/filtering (run_id, tenant_id, status, created_at, counts) plus a JSONB
`state` column holding the full serialized RunState. On read, the JSONB is
re-hydrated back into Pydantic models so the rest of the app is unchanged.

Public interface mirrors the in-memory RunStore exactly:
    put / get / list_ids / patch_draft / update_draft_send_result

Configure via SUPABASE_URL + SUPABASE_KEY (use the SERVICE_ROLE key on the
backend — it bypasses RLS). See `app/api/store.py::get_store` for selection.
"""
from __future__ import annotations

import logging
from typing import Any

from app.api.run_serde import deserialize_state, scalar_columns, serialize_state
from app.config import Settings
from app.graph.state import RunState

log = logging.getLogger("ap_agent.store.supabase")


def _row_payload(state: RunState) -> dict[str, Any]:
    """Build the table row: indexed columns + the full JSON state."""
    return {**scalar_columns(state), "state": serialize_state(state)}


class SupabaseRunStore:
    """Durable run store backed by a Supabase `runs` table."""

    backend_name = "supabase"

    def __init__(self, settings: Settings) -> None:
        # Lazy import so the package is only required when Supabase is used.
        from supabase import create_client

        self._table = settings.supabase_runs_table
        self._client = create_client(settings.supabase_url, settings.supabase_key)
        if settings.supabase_key.startswith("sb_publishable"):
            log.warning(
                "SUPABASE_KEY looks like a PUBLISHABLE/anon key. Backend writes "
                "may be blocked by RLS — use the SERVICE_ROLE key instead."
            )
        log.info("Supabase run store initialized (table=%s)", self._table)

    def ping(self) -> None:
        """Readiness probe — a bounded select that round-trips to PostgREST."""
        self._client.table(self._table).select("run_id").limit(1).execute()

    def put(self, state: RunState) -> None:
        payload = _row_payload(state)
        self._client.table(self._table).upsert(payload, on_conflict="run_id").execute()

    def get(self, run_id: str) -> RunState | None:
        resp = (
            self._client.table(self._table)
            .select("state")
            .eq("run_id", run_id)
            .limit(1)
            .execute()
        )
        data = resp.data or []
        if not data:
            return None
        return deserialize_state(data[0]["state"])

    def list_ids(self) -> list[str]:
        resp = (
            self._client.table(self._table)
            .select("run_id")
            .order("created_at", desc=True)
            .execute()
        )
        return [r["run_id"] for r in (resp.data or [])]

    def claim_draft_for_send(
        self, run_id: str, invoice_id: str, *, force: bool = False
    ) -> bool:
        """Claim a draft for sending (status → SENDING). Returns True iff the
        draft was in a claimable state.

        NOTE: this is a read-modify-write over PostgREST and is therefore only
        BEST-EFFORT against truly simultaneous requests — the nested draft state
        can't be guarded with a conditional REST update, and there's no row lock.
        It correctly serializes the common (sequential) case and blocks re-send
        of an already SENT/DRYRUN/SENDING draft. For race-proof claims across
        replicas, use the SQLAlchemy/DB backend (RUN_STORE_BACKEND=db), whose
        claim takes a real SELECT ... FOR UPDATE row lock. A stale SENDING claim
        (older than the TTL) is reclaimable so a crash mid-send self-heals.
        ``force=True`` allows reclaiming an already SENT/DRYRUN draft for an
        explicit operator resend."""
        from datetime import UTC, datetime

        from app.config import get_settings
        from app.schemas import SendStatus, claimable_for_send

        now = datetime.now(UTC)
        ttl = get_settings().comms_send_claim_ttl_seconds
        state = self.get(run_id)
        if not state:
            return False
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
                self.put(state)
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
        state = self.get(run_id)
        if not state:
            return False
        drafts = state.get("drafts", [])
        for i, d in enumerate(drafts):
            if d.invoice_id == invoice_id:
                drafts[i] = d.model_copy(
                    update={"subject": subject, "body": body, "is_edited_by_human": True}
                )
                state["drafts"] = drafts
                self.put(state)
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
        state = self.get(run_id)
        if not state:
            return False
        drafts = state.get("drafts", [])
        for i, d in enumerate(drafts):
            if d.invoice_id == invoice_id:
                drafts[i] = d.model_copy(
                    update={
                        "send_status": send_status,
                        "send_provider": send_provider,
                        "send_message_id": send_message_id,
                        "recipient": recipient,
                        "sent_at": sent_at,
                        "send_error": send_error,
                    }
                )
                state["drafts"] = drafts
                self.put(state)
                return True
        return False
