"""Human review endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException

from app.api.auth import Principal
from app.api.deps import get_owned_run, require_permission
from app.api.roles import DRAFT_EDIT, RUN_APPROVE
from app.api.store import get_store
from app.audit.logger import make_event
from app.schemas import AuditEventType, ResolutionPath, RunStatus
from app.schemas.case import Case, CaseStatus

router = APIRouter(prefix="/v1/runs", tags=["review"])


@router.get("/{run_id}/drafts/{invoice_id}")
def get_draft(run_id: str, invoice_id: str, state: dict = Depends(get_owned_run)) -> dict:
    for d in state.get("drafts", []):
        if d.invoice_id == invoice_id:
            return d.model_dump(mode="json")
    raise HTTPException(404, "draft not found")


@router.patch("/{run_id}/drafts/{invoice_id}")
def patch_draft(
    run_id: str,
    invoice_id: str,
    payload: dict = Body(...),
    _state: dict = Depends(get_owned_run),
    principal: Principal = Depends(require_permission(DRAFT_EDIT)),
) -> dict:
    store = get_store()
    body = payload.get("body")
    subject = payload.get("subject")
    if not body or not isinstance(body, str):
        raise HTTPException(400, "body required")
    # Bound the sizes — an email body/subject is short; a 10 MB paste is either
    # a mistake or abuse and would break downstream rendering/sending.
    if len(body) > 20_000:
        raise HTTPException(422, "body too long (max 20000 chars)")
    if subject is not None:
        if not isinstance(subject, str):
            raise HTTPException(400, "subject must be a string")
        if len(subject) > 500:
            raise HTTPException(422, "subject too long (max 500 chars)")
    ok = store.patch_draft(run_id, invoice_id, subject=subject, body=body)
    if not ok:
        raise HTTPException(404, "run or draft not found")
    state = store.get(run_id)
    assert state is not None
    state.setdefault("audit_events", []).append(
        make_event(
            run_id=run_id,
            invoice_id=invoice_id,
            node_name="review_api",
            event_type=AuditEventType.HUMAN_EDIT,
            actor=principal.subject or "unknown",
            metadata={"len_body": len(body), "role": principal.role},
        )
    )
    store.put(state)
    return {"status": "ok"}


@router.post("/{run_id}/resolutions/{invoice_id}/override")
def override_resolution(
    run_id: str,
    invoice_id: str,
    payload: dict = Body(...),
    _state: dict = Depends(get_owned_run),
    principal: Principal = Depends(require_permission(DRAFT_EDIT)),
) -> dict:
    """Human override of the agent's routing decision for one invoice.

    Records a RULE_OVERRIDE audit event (original rule + path → chosen path +
    reason) and updates the stored resolution. This is the auditable, controlled
    way to correct a mis-route — and it feeds the most-overridden-rules report so
    each org's rulebook can be tuned from real corrections. (Policy edits never
    retroactively re-route past runs; this is the explicit per-invoice mechanism.)
    """
    path_raw = (payload.get("resolution_path") or "").strip()
    reason = (payload.get("reason") or "").strip()
    try:
        new_path = ResolutionPath(path_raw)
    except ValueError:
        valid = ", ".join(p.value for p in ResolutionPath)
        raise HTTPException(400, f"invalid resolution_path '{path_raw}'. Valid: {valid}") from None
    if not reason:
        raise HTTPException(422, "a reason is required for an override")

    store = get_store()
    state = store.get(run_id)
    if state is None:
        raise HTTPException(404, "run not found")
    resolutions = state.get("resolutions", [])
    target = next((r for r in resolutions if r.invoice_id == invoice_id), None)
    if target is None:
        raise HTTPException(404, f"no resolution for invoice {invoice_id}")
    if target.resolution_path == new_path:
        return {"status": "noop", "invoice_id": invoice_id, "resolution_path": new_path.value}

    base_rule_id = target.rule_id.split("+", 1)[0]  # strip any prior override marker
    original_path = target.resolution_path
    updated = target.model_copy(
        update={
            "resolution_path": new_path,
            "rule_id": f"{base_rule_id}+human_override",
            "rule_trace": [
                *target.rule_trace,
                f"HUMAN OVERRIDE: {original_path.value} → {new_path.value} "
                f"by {principal.subject or 'unknown'}: {reason}",
            ],
        }
    )
    state["resolutions"] = [updated if r.invoice_id == invoice_id else r for r in resolutions]
    state.setdefault("audit_events", []).append(
        make_event(
            run_id=run_id,
            invoice_id=invoice_id,
            node_name="review_api",
            event_type=AuditEventType.RULE_OVERRIDE,
            actor=principal.subject or "unknown",
            metadata={
                "original_rule_id": base_rule_id,
                "original_path": original_path.value,
                "new_path": new_path.value,
                "reason": reason[:500],
                "role": principal.role,
            },
        )
    )
    store.put(state)
    return {
        "status": "ok",
        "invoice_id": invoice_id,
        "resolution_path": new_path.value,
        "original_path": original_path.value,
        "original_rule_id": base_rule_id,
    }


@router.post("/{run_id}/approve")
def approve_run(
    run_id: str,
    state: dict = Depends(get_owned_run),
    principal: Principal = Depends(require_permission(RUN_APPROVE)),
) -> dict:
    store = get_store()
    state["status"] = RunStatus.COMPLETED
    state.setdefault("audit_events", []).append(
        make_event(
            run_id=run_id,
            node_name="review_api",
            event_type=AuditEventType.APPROVAL,
            actor=principal.subject or "unknown",
            metadata={"role": principal.role},
        )
    )
    store.put(state)
    return {"run_id": run_id, "status": "COMPLETED"}


@router.get("/{run_id}/cases")
def list_cases(run_id: str, state: dict = Depends(get_owned_run)) -> dict:
    """Per-invoice resolution lifecycle (Open → In progress → Resolved / Won't fix).

    Returns only invoices a human has acted on; the UI treats any invoice with no
    entry as OPEN.
    """
    return {"run_id": run_id, "cases": state.get("cases", {})}


@router.patch("/{run_id}/cases/{invoice_id}")
def update_case(
    run_id: str,
    invoice_id: str,
    payload: dict = Body(...),
    state: dict = Depends(get_owned_run),
    principal: Principal = Depends(require_permission(DRAFT_EDIT)),
) -> dict:
    """Advance an exception's resolution lifecycle. Append-only audited (CASE_UPDATE)."""
    from datetime import UTC, datetime

    status_raw = (payload.get("status") or "").strip()
    note = (payload.get("note") or "").strip() or None
    try:
        new_status = CaseStatus(status_raw)
    except ValueError:
        valid = ", ".join(s.value for s in CaseStatus)
        raise HTTPException(400, f"invalid status '{status_raw}'. Valid: {valid}") from None

    # The invoice must belong to this run.
    if invoice_id not in {r.invoice_id for r in state.get("rows", [])}:
        raise HTTPException(404, f"no invoice {invoice_id} in this run")

    cases = dict(state.get("cases", {}))
    prev = cases.get(invoice_id, {}).get("status", CaseStatus.OPEN.value)
    case = Case(
        invoice_id=invoice_id,
        status=new_status,
        note=note,
        updated_at=datetime.now(UTC),
        updated_by=principal.subject or "unknown",
    ).model_dump(mode="json")
    cases[invoice_id] = case
    state["cases"] = cases

    store = get_store()
    state.setdefault("audit_events", []).append(
        make_event(
            run_id=run_id,
            invoice_id=invoice_id,
            node_name="review_api",
            event_type=AuditEventType.CASE_UPDATE,
            actor=principal.subject or "unknown",
            metadata={
                "from": prev,
                "to": new_status.value,
                "note": (note or "")[:500],
                "role": principal.role,
            },
        )
    )
    store.put(state)
    return {"status": "ok", "case": case}
