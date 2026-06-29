"""Map a completed RunState into the normalized tables.

Deterministic UUIDs (uuid5 of run_id / invoice_id) make persistence idempotent:
re-persisting the same run replaces its batch (cascade) rather than duplicating.
Called from persist_node when DB_PERSISTENCE_ENABLED=true.
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select

from app.config import get_settings
from app.db import models as m
from app.db.session import init_db, session_scope
from app.graph.state import RunState

log = logging.getLogger("ap_agent.db.persistence")

# Fixed namespace so the same logical entity always maps to the same UUID.
_NS = uuid.UUID("0a5e8b9c-2d3f-4a1b-8c7d-1e2f3a4b5c6d")

_STATUS_BY_PATH = {
    "AUTO_APPROVE": "Auto Approved",
    "ESCALATE_CONTROLLER": "Escalated",
    "HOLD_INVESTIGATION": "Pending Finance Review",
    "REQUEST_PO": "Pending Requestor",
    "REQUEST_GRN": "Pending Requestor",
    "PROCUREMENT_REVIEW": "Pending Requestor",
    "VENDOR_VALIDATION_REVIEW": "Pending Vendor",
    "MANUAL_REVIEW": "Classified",
}
_EMAIL_TYPE_BY_CHANNEL = {
    "vendor_email": "Vendor Query",
    "internal_email": "Internal Request",
    "slack": "Finance Escalation",
    "finance_note": "Finance Escalation",
}
_DELIVERY_BY_SEND = {
    "sent": "Sent",
    "dryrun": "Sent",
    "delivered": "Delivered",
    "failed": "Failed",
    "skipped": "Draft",
    "draft": "Draft",
}


def _u(*parts: str) -> uuid.UUID:
    return uuid.uuid5(_NS, ":".join(parts))


def _enum_val(v):
    return v.value if hasattr(v, "value") else v


def persist_run(state: RunState) -> None:
    """Persist a finished run into the normalized schema. No-op when disabled."""
    if not get_settings().db_persistence_enabled:
        return
    try:
        _persist(state)
    except Exception:  # never let persistence break the pipeline
        log.exception("normalized persistence failed for run_id=%s", state.get("run_id"))


def _persist(state: RunState) -> None:
    init_db()
    run_id = state["run_id"]
    tenant = state.get("tenant_id", "default")
    rows = list(state.get("rows", []))
    quarantined = list(state.get("quarantined", []))
    classifications = {c.invoice_id: c for c in state.get("classifications", [])}
    resolutions = {r.invoice_id: r for r in state.get("resolutions", [])}
    drafts = state.get("drafts", [])
    drafts_by_inv: dict[str, list] = {}
    for d in drafts:
        drafts_by_inv.setdefault(d.invoice_id, []).append(d)

    # priority lookup (entry + rank within bucket order)
    pq = state.get("priority_queues")
    prio_by_inv: dict[str, tuple] = {}
    if pq is not None:
        for bucket_name in ("high", "medium", "low"):
            for rank, entry in enumerate(getattr(pq, bucket_name, []) or [], start=1):
                prio_by_inv[entry.invoice_id] = (entry, rank)

    created_at = state.get("created_at") or datetime.now(UTC)
    completed_at = state.get("completed_at")
    batch_id = _u(run_id)
    valid_invoices = {r.invoice_id for r in rows}

    with session_scope() as s:
        # Idempotency: explicitly clear any prior rows for this batch in
        # child -> parent order. Explicit (not FK cascade) so it works on
        # SQLite too, and covers agent_executions which has no ORM relationship.
        exc_ids = select(m.ExceptionRecord.exception_id).where(
            m.ExceptionRecord.batch_id == batch_id
        )
        for child in (m.Classification, m.Resolution, m.Priority, m.Communication, m.StatusHistory):
            s.execute(delete(child).where(child.exception_id.in_(exc_ids)))
        s.execute(delete(m.AgentExecution).where(m.AgentExecution.batch_id == batch_id))
        s.execute(delete(m.ExceptionRecord).where(m.ExceptionRecord.batch_id == batch_id))
        s.execute(delete(m.UploadBatch).where(m.UploadBatch.batch_id == batch_id))
        s.flush()

        s.add(
            m.UploadBatch(
                batch_id=batch_id,
                tenant_id=tenant,
                file_name=state.get("source_filename") or "upload",
                source_file_hash=state.get("source_file_hash"),
                total_records=len(rows) + len(quarantined),
                processed_records=len(rows),
                failed_records=len(quarantined),
                status="Failed" if _enum_val(state.get("status")) == "FAILED" else "Completed",
                uploaded_by="system",
                upload_time=created_at,
                completed_at=completed_at,
            )
        )

        # Vendors: ensure a row exists for the exception FK, but NEVER overwrite
        # the profile/counters — the vendor store (DbVendorProfileStore) owns
        # those. Same keying (vendor_id_for) so both agree on one row per vendor.
        from app.vendor.store import _VENDOR_TENANT, vendor_id_for

        seen_vendors: set[str] = set()
        for row in rows:
            if row.vendor_name in seen_vendors:
                continue
            seen_vendors.add(row.vendor_name)
            vid = vendor_id_for(row.vendor_name)
            if s.get(m.Vendor, vid) is None:
                s.add(
                    m.Vendor(
                        vendor_id=vid,
                        tenant_id=_VENDOR_TENANT,
                        vendor_name=row.vendor_name,
                        first_seen_at=created_at,
                        last_seen_at=created_at,
                    )
                )

        # Write batch + vendors before the exceptions that reference them.
        s.flush()

        for row in rows:
            inv = row.invoice_id
            exc_id = _u(run_id, inv)
            c = classifications.get(inv)
            r = resolutions.get(inv)
            status = (
                _STATUS_BY_PATH.get(_enum_val(r.resolution_path), "Classified")
                if r is not None
                else ("Classified" if c is not None else "New")
            )

            s.add(
                m.ExceptionRecord(
                    exception_id=exc_id,
                    batch_id=batch_id,
                    vendor_id=vendor_id_for(row.vendor_name),
                    tenant_id=tenant,
                    invoice_id=inv,
                    vendor_name=row.vendor_name,
                    invoice_amount=row.invoice_amount,
                    po_number=row.po_number,
                    exception_type=row.exception_type,
                    exception_description=row.exception_description,
                    days_outstanding=row.days_outstanding,
                    approver_assigned=row.approver_assigned,
                    source_file_name=state.get("source_filename"),
                    uploaded_by="system",
                    upload_timestamp=created_at,
                    current_status=status,
                )
            )

            if c is not None:
                s.add(
                    m.Classification(
                        classification_id=_u(run_id, inv, "cls"),
                        exception_id=exc_id,
                        primary_exception_type=_enum_val(c.primary_exception_type),
                        root_cause_hypothesis=c.root_cause,
                        confidence_score=c.confidence_score,
                        severity=_enum_val(c.severity),
                        severity_ai_suggested=_enum_val(c.severity_ai_suggested),
                        ai_reasoning=c.rationale,
                        model_id=c.model_id,
                        prompt_version=c.prompt_version,
                        classified_timestamp=created_at,
                    )
                )

            if r is not None:
                s.add(
                    m.Resolution(
                        resolution_id=_u(run_id, inv, "res"),
                        exception_id=exc_id,
                        resolution_path=_enum_val(r.resolution_path),
                        resolution_status=status,
                        rule_id=r.rule_id,
                        rule_version=r.rule_version,
                        sla_hours=r.sla_hours,
                        requires_communication=r.requires_communication,
                    )
                )

            entry_rank = prio_by_inv.get(inv)
            if entry_rank is not None:
                entry, rank = entry_rank
                s.add(
                    m.Priority(
                        priority_id=_u(run_id, inv, "pri"),
                        exception_id=exc_id,
                        priority_score=entry.priority_score,
                        priority_bucket=_enum_val(entry.bucket),
                        ranking_position=rank,
                        drivers=list(entry.drivers),
                        last_priority_update=created_at,
                    )
                )

            for i, d in enumerate(drafts_by_inv.get(inv, [])):
                s.add(
                    m.Communication(
                        email_id=_u(run_id, inv, "comm", str(i)),
                        exception_id=exc_id,
                        email_type=_EMAIL_TYPE_BY_CHANNEL.get(_enum_val(d.channel), "Internal Request"),
                        channel=_enum_val(d.channel),
                        recipient_email=d.recipient or d.recipient_hint,
                        subject=d.subject,
                        email_body=d.body,
                        template_id=d.template_id,
                        generated_by_ai=not d.is_edited_by_human,
                        model_id=d.model_id,
                        sent_flag=_enum_val(d.send_status) in ("sent", "dryrun"),
                        sent_timestamp=d.sent_at,
                        delivery_status=_DELIVERY_BY_SEND.get(_enum_val(d.send_status), "Draft"),
                        provider=d.send_provider,
                        message_id=d.send_message_id,
                        error_message=d.send_error,
                    )
                )

            # lifecycle: New -> current
            s.add(
                m.StatusHistory(
                    history_id=_u(run_id, inv, "hist", "0"),
                    exception_id=exc_id,
                    old_status=None,
                    new_status="New",
                    changed_by="system",
                    comments="Ingested",
                    changed_timestamp=created_at,
                )
            )
            if status != "New":
                s.add(
                    m.StatusHistory(
                        history_id=_u(run_id, inv, "hist", "1"),
                        exception_id=exc_id,
                        old_status="New",
                        new_status=status,
                        changed_by="agent",
                        comments=f"Routed via {_enum_val(r.resolution_path)}" if r else "Classified",
                        changed_timestamp=created_at,
                    )
                )

        # Write all exceptions + children before the agent-execution audit rows
        # that reference them (keeps FK checks happy on SQLite and Postgres).
        s.flush()

        # Agent execution audit (from the run's audit events). Key the PK by
        # position so it's collision-proof even if two events share an id.
        for i, ev in enumerate(state.get("audit_events", [])):
            inv = getattr(ev, "invoice_id", None)
            exc_ref = _u(run_id, inv) if inv in valid_invoices else None
            et = _enum_val(ev.event_type)
            s.add(
                m.AgentExecution(
                    execution_id=_u(run_id, "exec", str(i)),
                    batch_id=batch_id,
                    exception_id=exc_ref,
                    node_name=ev.node_name,
                    node_output=ev.metadata or None,
                    success_flag=et != "ERROR",
                    error_message=(ev.metadata or {}).get("message") if et == "ERROR" else None,
                    execution_timestamp=ev.timestamp,
                )
            )

    log.info("normalized persistence OK run_id=%s exceptions=%d", run_id, len(rows))
