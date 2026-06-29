"""Outbound send endpoints — explicit human action required.

POST /v1/runs/{run_id}/drafts/{invoice_id}/send
    Send one draft. Returns the SendResult.

POST /v1/runs/{run_id}/drafts/send_all
    Bulk-send. Body: {"invoice_ids": ["INV-2001", ...]}. Returns one
    SendResult per requested invoice.

GET  /v1/runs/{run_id}/sent
    List the send results for every draft in this run.

There is no auto-send. The pipeline never reaches these endpoints on its
own; they exist solely for the reviewer console.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from app.api.auth import Principal
from app.api.deps import get_owned_run, require_permission
from app.api.org_config import resolve_settings
from app.api.roles import COMMS_SEND
from app.api.store import get_store
from app.audit.logger import make_event
from app.comms import dispatch
from app.comms.dispatcher import CONSOLIDATABLE_CHANNELS, dispatch_consolidated
from app.comms.recipients import resolve_recipient
from app.schemas import AuditEventType, SendStatus

log = logging.getLogger("ap_agent.routes_comms")

router = APIRouter(prefix="/v1/runs", tags=["comms"])


def _serialize(result, draft_invoice_id: str) -> dict:
    return {
        "invoice_id": result.invoice_id or draft_invoice_id,
        "status": result.status.value,
        "provider": result.provider,
        "message_id": result.message_id,
        "recipient": result.recipient,
        "sent_at": result.sent_at.isoformat() if result.sent_at else None,
        "error_message": result.error_message,
    }


def _serialize_draft(d) -> dict:
    """Report a draft's already-recorded send outcome (idempotent re-send)."""
    return {
        "invoice_id": d.invoice_id,
        "status": d.send_status.value,
        "provider": d.send_provider,
        "message_id": d.send_message_id,
        "recipient": d.recipient,
        "sent_at": d.sent_at.isoformat() if d.sent_at else None,
        "error_message": d.send_error,
    }


def _current_draft(store, run_id: str, invoice_id: str):
    """Re-read a single draft's current state from the store (post-claim check)."""
    fresh = store.get(run_id) or {}
    return next(
        (d for d in fresh.get("drafts", []) if d.invoice_id == invoice_id), None
    )


def _slack_context(state, invoice_id: str) -> dict:
    """Structured metadata for the Slack Block Kit fields, pulled from run state."""
    ctx: dict = {}
    row = next((r for r in state.get("rows", []) if r.invoice_id == invoice_id), None)
    c = next((c for c in state.get("classifications", []) if c.invoice_id == invoice_id), None)
    res = next((x for x in state.get("resolutions", []) if x.invoice_id == invoice_id), None)
    if row is not None:
        ctx["vendor_name"] = row.vendor_name
        ctx["invoice_amount"] = float(row.invoice_amount)
        ctx["days_outstanding"] = row.days_outstanding
    if c is not None:
        ctx["severity"] = c.severity.value
        ctx["exception_type"] = c.primary_exception_type.value
    if res is not None:
        # Carry the RAW routing code — the Slack renderer (_build_blocks) maps it
        # to the friendly "Recommended approach" label via resolution_path_label,
        # so the label lives in exactly one place.
        ctx["resolution_path"] = res.resolution_path.value
        ctx["sla_hours"] = res.sla_hours
    return ctx


@router.post("/{run_id}/drafts/{invoice_id}/send")
def send_draft(
    run_id: str,
    invoice_id: str,
    body: dict[str, Any] | None = Body(default=None),
    _owned: dict = Depends(get_owned_run),
    principal: Principal = Depends(require_permission(COMMS_SEND)),
) -> dict:
    # Resolve per-org comms credentials (BYOK) for this run's tenant.
    settings = resolve_settings(_owned.get("tenant_id") or "default")
    store = get_store()
    state = store.get(run_id)
    if state is None:
        raise HTTPException(404, "run not found")

    target = next(
        (d for d in state.get("drafts", []) if d.invoice_id == invoice_id),
        None,
    )
    if target is None:
        raise HTTPException(404, f"no draft for invoice {invoice_id}")

    # An explicit operator "Resend" re-resolves the recipient from the current
    # vendor directory (so an edited vendor email is honoured) and is allowed to
    # re-send an already-sent draft. A plain "Send" stays idempotent.
    resend = bool((body or {}).get("resend"))

    # Atomically claim the draft so two concurrent send requests can't both
    # dispatch and double-send it. A lost claim means it's already sent
    # (return that result idempotently — unless this is an explicit resend) or a
    # send is in flight (409).
    if not store.claim_draft_for_send(run_id, invoice_id, force=resend):
        cur = _current_draft(store, run_id, invoice_id)
        if not resend and cur is not None and cur.send_status in (SendStatus.SENT, SendStatus.DRYRUN):
            return _serialize_draft(cur)
        raise HTTPException(409, f"a send for invoice {invoice_id} is already in progress")

    override = (body or {}).get("recipient_override")
    try:
        result = dispatch(
            draft=target,
            run_id=run_id,
            settings=settings,
            recipient_override=override,
            context=_slack_context(state, invoice_id),
            tenant_id=_owned.get("tenant_id") or "default",
            force=resend,
        )
    except Exception:  # noqa: BLE001 — never leave the draft wedged in SENDING
        store.update_draft_send_result(
            run_id, invoice_id, send_status=SendStatus.FAILED, send_provider=None,
            send_message_id=None, recipient=None, sent_at=None,
            send_error="send raised an unexpected error",
        )
        raise

    store.update_draft_send_result(
        run_id,
        invoice_id,
        send_status=result.status,
        send_provider=result.provider,
        send_message_id=result.message_id,
        recipient=result.recipient,
        sent_at=result.sent_at,
        send_error=result.error_message,
    )

    # Stamp audit event regardless of outcome
    state = store.get(run_id)
    if state is not None:
        state.setdefault("audit_events", []).append(
            make_event(
                run_id=run_id,
                invoice_id=invoice_id,
                node_name="comms_dispatch",
                event_type=AuditEventType.HUMAN_EDIT
                if result.status == SendStatus.SENT
                else AuditEventType.ERROR
                if result.status == SendStatus.FAILED
                else AuditEventType.APPROVAL,
                actor=principal.subject or "unknown",
                metadata={
                    "send_status": result.status.value,
                    "provider": result.provider,
                    "message_id": result.message_id,
                    "recipient": result.recipient,
                    "error": result.error_message,
                    "dryrun": settings.comms_dryrun,
                    "role": principal.role,
                },
            )
        )
        store.put(state)

    return _serialize(result, invoice_id)


def _record_and_serialize(store, run_id, inv_id, result, *, consolidated=False) -> dict:
    store.update_draft_send_result(
        run_id, inv_id, send_status=result.status, send_provider=result.provider,
        send_message_id=result.message_id, recipient=result.recipient,
        sent_at=result.sent_at, send_error=result.error_message,
    )
    out = _serialize(result, inv_id)
    out["invoice_id"] = inv_id  # result carries a group id for consolidated sends
    if consolidated:
        out["consolidated"] = True
    return out


def _send_already_claimed(store, run_id, target, inv_id, *, settings, state, tenant_id) -> dict:
    """Dispatch a single draft that has ALREADY been claimed (status SENDING)."""
    try:
        result = dispatch(
            draft=target, run_id=run_id, settings=settings,
            context=_slack_context(state, inv_id), tenant_id=tenant_id,
        )
    except Exception:  # noqa: BLE001 — never leave the draft wedged in SENDING
        store.update_draft_send_result(
            run_id, inv_id, send_status=SendStatus.FAILED, send_provider=None,
            send_message_id=None, recipient=None, sent_at=None,
            send_error="send raised an unexpected error",
        )
        return {
            "invoice_id": inv_id, "status": "failed", "provider": "none",
            "message_id": None, "recipient": None, "sent_at": None,
            "error_message": "send raised an unexpected error",
        }
    return _record_and_serialize(store, run_id, inv_id, result)


def _claim_or_report(store, run_id, inv_id) -> dict | None:
    """Claim a draft for sending. Returns None on success, or a result dict to
    report when the claim is lost (already sent → idempotent; in flight → skip)."""
    if store.claim_draft_for_send(run_id, inv_id):
        return None
    cur = _current_draft(store, run_id, inv_id)
    if cur is not None and cur.send_status in (SendStatus.SENT, SendStatus.DRYRUN):
        return _serialize_draft(cur)
    return {
        "invoice_id": inv_id, "status": "skipped", "provider": "none",
        "message_id": None, "recipient": None, "sent_at": None,
        "error_message": "a send for this draft is already in progress",
    }


@router.post("/{run_id}/drafts/send_all")
def send_all(
    run_id: str,
    body: dict[str, Any] = Body(...),
    _owned: dict = Depends(get_owned_run),
    principal: Principal = Depends(require_permission(COMMS_SEND)),
) -> dict:
    """Bulk-send drafts. Invoices that resolve to the SAME email recipient are
    coalesced into ONE consolidated email (summary + per-invoice sections) rather
    than one email each — so 100 invoices to one inbox is 1 message, not 100.
    Pass ``{"consolidate": false}`` to force one email per invoice."""
    tenant_id = _owned.get("tenant_id") or "default"
    settings = resolve_settings(tenant_id)
    store = get_store()
    state = store.get(run_id)
    if state is None:
        raise HTTPException(404, "run not found")

    requested_ids = body.get("invoice_ids") or []
    if not isinstance(requested_ids, list) or not requested_ids:
        raise HTTPException(400, "invoice_ids must be a non-empty list")
    requested_ids = list(dict.fromkeys(requested_ids))  # de-dupe (preserve order)
    consolidate = bool(body.get("consolidate", True))

    drafts_by_id = {d.invoice_id: d for d in state.get("drafts", [])}
    rows_by_id = {r.invoice_id: r for r in state.get("rows", [])}
    results: list[dict] = []

    # Partition into (channel, recipient) groups for email channels; everything
    # else (Slack, unresolved recipient, consolidate=off) sends per draft.
    groups: dict[tuple, list] = {}
    singles: list[tuple] = []
    for inv_id in requested_ids:
        target = drafts_by_id.get(inv_id)
        if target is None:
            results.append({
                "invoice_id": inv_id, "status": "skipped", "provider": "none",
                "message_id": None, "recipient": None, "sent_at": None,
                "error_message": "draft not found",
            })
            continue
        recipient = None
        if consolidate and target.channel in CONSOLIDATABLE_CHANNELS:
            row = rows_by_id.get(inv_id)
            recipient = resolve_recipient(
                draft=target, settings=settings, vendor_name=getattr(row, "vendor_name", None),
                tenant_id=tenant_id,
            )
        if recipient and "@" in recipient:
            groups.setdefault((target.channel, recipient), []).append((inv_id, target))
        else:
            singles.append((inv_id, target))

    # Consolidated groups (2+ invoices to one recipient) → one email.
    for (channel, recipient), members in groups.items():
        if len(members) == 1:
            singles.append(members[0])
            continue
        claimed: list[tuple] = []
        for inv_id, target in members:
            report = _claim_or_report(store, run_id, inv_id)
            if report is None:
                claimed.append((inv_id, target))
            else:
                results.append(report)
        if not claimed:
            continue
        if len(claimed) == 1:  # only one survived the claim — send it as a single
            inv_id, target = claimed[0]
            results.append(
                _send_already_claimed(store, run_id, target, inv_id,
                                      settings=settings, state=state, tenant_id=tenant_id)
            )
            continue
        try:
            result = dispatch_consolidated(
                recipient=recipient, channel=channel,
                drafts=[t for _, t in claimed], rows_by_id=rows_by_id,
                run_id=run_id, settings=settings, tenant_id=tenant_id,
            )
        except Exception:  # noqa: BLE001 — never leave claimed drafts wedged
            for inv_id, _t in claimed:
                store.update_draft_send_result(
                    run_id, inv_id, send_status=SendStatus.FAILED, send_provider=None,
                    send_message_id=None, recipient=recipient, sent_at=None,
                    send_error="consolidated send raised an unexpected error",
                )
                results.append({
                    "invoice_id": inv_id, "status": "failed", "provider": "none",
                    "message_id": None, "recipient": recipient, "sent_at": None,
                    "error_message": "consolidated send raised an unexpected error",
                    "consolidated": True,
                })
            continue
        for inv_id, _t in claimed:
            results.append(
                _record_and_serialize(store, run_id, inv_id, result, consolidated=True)
            )

    # Singles (per-draft): claim then dispatch.
    for inv_id, target in singles:
        report = _claim_or_report(store, run_id, inv_id)
        if report is not None:
            results.append(report)
            continue
        results.append(
            _send_already_claimed(store, run_id, target, inv_id,
                                  settings=settings, state=state, tenant_id=tenant_id)
        )

    consolidated_count = sum(1 for r in results if r.get("consolidated"))
    return {
        "run_id": run_id,
        "dryrun": settings.comms_dryrun,
        "results": results,
        "summary": {
            "sent": sum(1 for r in results if r["status"] == "sent"),
            "dryrun": sum(1 for r in results if r["status"] == "dryrun"),
            "failed": sum(1 for r in results if r["status"] == "failed"),
            "skipped": sum(1 for r in results if r["status"] == "skipped"),
            "consolidated_invoices": consolidated_count,
        },
    }


@router.get("/{run_id}/sent")
def list_sent(run_id: str, state: dict = Depends(get_owned_run)) -> dict:
    rows = []
    for d in state.get("drafts", []):
        rows.append(
            {
                "invoice_id": d.invoice_id,
                "channel": d.channel.value,
                "template_id": d.template_id,
                "send_status": d.send_status.value,
                "send_provider": d.send_provider,
                "send_message_id": d.send_message_id,
                "recipient": d.recipient,
                "sent_at": d.sent_at.isoformat() if d.sent_at else None,
                "send_error": d.send_error,
            }
        )
    return {"run_id": run_id, "drafts": rows, "total": len(rows)}
