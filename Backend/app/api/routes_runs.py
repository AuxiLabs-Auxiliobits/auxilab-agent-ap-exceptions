"""POST /v1/runs, GET /v1/runs/{id}, /v1/runs/{id}/results, /v1/runs/{id}/audit."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Response, UploadFile

from app.api.auth import Principal, require_auth
from app.api.deps import get_owned_run, require_permission
from app.api.roles import RUN_CREATE
from app.api.runner import submit_run
from app.api.store import get_store
from app.schemas import RunStatus, RunSummary
from app.upload_format import rejection_csv

router = APIRouter(prefix="/v1/runs", tags=["runs"])

# Reject uploads larger than this. The pipeline is bounded by row-count
# concurrency anyway; this is purely a defensive memory cap.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


@router.post("", response_model=RunSummary)
async def create_run(
    file: UploadFile = File(...),
    tenant_id: str = Form("default"),
    principal: Principal = Depends(require_permission(RUN_CREATE)),
) -> RunSummary:
    """Schedule a run as a background task; returns immediately.

    Clients should poll `GET /v1/runs/{run_id}` until status is one of
    AWAITING_REVIEW, COMPLETED, or FAILED.
    """
    if not file.filename:
        raise HTTPException(400, "filename required")
    content = await file.read()
    size = len(content)
    if size == 0:
        raise HTTPException(400, "empty file")
    if size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413,
            f"file too large: {size} bytes (max {MAX_UPLOAD_BYTES})",
        )

    # When auth is on, the run is owned by the caller's tenant — never trust a
    # client-supplied tenant_id. In dev (auth off) keep the form value.
    effective_tenant = tenant_id if principal.subject == "dev" else principal.tenant_id

    store = get_store()
    run_id = await submit_run(
        content=content,
        filename=file.filename,
        tenant_id=effective_tenant,
        store=store,
        owner=principal.subject,  # so the uploader sees this run from any browser/org
    )

    state = store.get(run_id)
    assert state is not None, "store.put should have happened inside submit_run"
    return RunSummary(
        run_id=run_id,
        tenant_id=state["tenant_id"],
        status=state.get("status", RunStatus.RUNNING),
        created_at=state["created_at"],
        rows_accepted=len(state.get("rows", [])),
        rows_quarantined=len(state.get("quarantined", [])),
        current_node=state.get("current_node"),
    )


@router.get("")
def list_runs(principal: Principal = Depends(require_auth)) -> dict:
    """List runs (newest first) visible to the caller.

    Visible = runs in the caller's tenant (org) OR runs the caller uploaded.
    Scoping by uploader too means a user sees their own runs from any browser or
    org context (Clerk's active org is per-browser), not just the org currently
    selected. The dev principal (auth off) sees everything.

    NOTE: the in-memory store loses these on restart — this reflects only runs
    created since the server last started.
    """
    store = get_store()
    runs = []
    for rid in store.list_ids():
        state = store.get(rid)
        if state is None:
            continue
        # Visibility: own-tenant OR own-upload (skipped for the dev principal).
        if principal.subject != "dev" and not (
            state.get("tenant_id") == principal.tenant_id
            or state.get("owner") == principal.subject
        ):
            continue
        runs.append(
            {
                "run_id": state["run_id"],
                "tenant_id": state["tenant_id"],
                "status": state["status"],
                "created_at": state["created_at"],
                "rows_accepted": len(state.get("rows", [])),
                "rows_quarantined": len(state.get("quarantined", [])),
                "current_node": state.get("current_node"),
            }
        )
    runs.sort(key=lambda r: r["created_at"], reverse=True)
    return {"runs": runs, "total": len(runs)}


@router.get("/{run_id}")
def get_run(run_id: str, state: dict = Depends(get_owned_run)) -> dict:
    return _summarize(state)


@router.get("/{run_id}/results")
def get_run_results(
    run_id: str,
    limit: int | None = Query(default=None, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    state: dict = Depends(get_owned_run),
) -> dict:
    """Per-invoice results. Returns all rows by default; pass limit/offset to
    paginate large runs (response includes `total`)."""
    rows_by_id = {r.invoice_id: r for r in state.get("rows", [])}
    c_by_id = {c.invoice_id: c for c in state.get("classifications", [])}
    r_by_id = {x.invoice_id: x for x in state.get("resolutions", [])}
    d_by_id = {d.invoice_id: d for d in state.get("drafts", [])}
    total = len(rows_by_id)
    items = list(rows_by_id.items())
    if limit is not None:
        items = items[offset : offset + limit]
    elif offset:
        items = items[offset:]
    out = []
    for inv_id, row in items:
        out.append(
            {
                "invoice_id": inv_id,
                "row": row.model_dump(mode="json"),
                "classification": c_by_id[inv_id].model_dump(mode="json")
                if inv_id in c_by_id
                else None,
                "resolution": r_by_id[inv_id].model_dump(mode="json")
                if inv_id in r_by_id
                else None,
                "draft": d_by_id[inv_id].model_dump(mode="json")
                if inv_id in d_by_id
                else None,
            }
        )
    return {"run_id": run_id, "count": len(out), "total": total, "results": out}


@router.get("/{run_id}/duplicates")
def get_historical_duplicates(
    run_id: str,
    state: dict = Depends(get_owned_run),
    principal: Principal = Depends(require_auth),
) -> dict:
    """Flag invoices in this run that ALSO appear in the tenant's *other* runs.

    Overpayment / double-pay guard: the same ``invoice_id`` processed in another
    run likely means the invoice was already handled (and possibly paid) before.
    In-file duplicates are caught at ingest; this is the cross-run check.

    Exact ``invoice_id`` match, scoped to the caller's tenant, best-effort over
    whatever runs the store currently holds (the in-memory store only sees runs
    since the last restart; the durable DB store sees full history).
    """
    store = get_store()
    tenant_id = state.get("tenant_id")

    # Index invoice_id -> prior occurrences across all OTHER runs of this tenant.
    index: dict[str, list[dict]] = {}
    runs_scanned = 0
    for rid in store.list_ids():
        if rid == run_id:
            continue
        other = store.get(rid)
        if other is None:
            continue
        # Tenant scoping (the dev principal sees all, matching list_runs()).
        if principal.subject != "dev" and other.get("tenant_id") != tenant_id:
            continue
        runs_scanned += 1
        for row in other.get("rows", []):
            index.setdefault(row.invoice_id, []).append(
                {
                    "run_id": other["run_id"],
                    "created_at": other["created_at"],
                    "invoice_amount": str(row.invoice_amount),
                    "vendor_name": row.vendor_name,
                }
            )

    rows = state.get("rows", [])
    duplicates = []
    for row in rows:
        occ = index.get(row.invoice_id)
        if not occ:
            continue
        cur_amount = str(row.invoice_amount)
        occurrences = [
            {**o, "amount_matches": o["invoice_amount"] == cur_amount}
            for o in sorted(occ, key=lambda o: o["created_at"], reverse=True)
        ]
        duplicates.append(
            {
                "invoice_id": row.invoice_id,
                "vendor_name": row.vendor_name,
                "invoice_amount": cur_amount,
                "occurrences": occurrences,
            }
        )

    # Most recently seen prior occurrence first.
    duplicates.sort(key=lambda d: d["occurrences"][0]["created_at"], reverse=True)
    return {
        "run_id": run_id,
        "checked": len(rows),
        "runs_scanned": runs_scanned,
        "duplicate_count": len(duplicates),
        "duplicates": duplicates,
    }


@router.get("/{run_id}/audit")
def get_run_audit(run_id: str, state: dict = Depends(get_owned_run)) -> dict:
    return {
        "run_id": run_id,
        "events": [e.model_dump(mode="json") for e in state.get("audit_events", [])],
    }


@router.post("/{run_id}/ask")
async def ask_desk(
    run_id: str,
    payload: dict = Body(...),
    state: dict = Depends(get_owned_run),
) -> dict:
    """'Ask the desk' — a read-only, grounded Q&A over this run's real data.

    Hybrid: the LLM understands the free-form question and (for open-ended
    questions) RAG retrieves the relevant invoices, but every figure is computed
    deterministically from run state — the assistant can't invent a number and
    never decides or acts. With no LLM configured it falls back to a deterministic
    keyword engine, so the endpoint always answers.
    """
    from datetime import UTC, datetime

    from app.api.assistant_hybrid import answer_question_hybrid

    question = (payload.get("question") or "").strip()
    if not question:
        raise HTTPException(400, "question is required")
    if len(question) > 500:
        raise HTTPException(422, "question too long (max 500 chars)")
    result = await answer_question_hybrid(state, question, now=datetime.now(UTC))
    return {"run_id": run_id, "question": question, **result}


@router.get("/{run_id}/errors")
def get_run_errors(run_id: str, state: dict = Depends(get_owned_run)) -> dict:
    """Record-level validation report: every row rejected at ingest with its
    reason code and the original values."""
    quarantined = state.get("quarantined", [])
    return {
        "run_id": run_id,
        "count": len(quarantined),
        "errors": [q.model_dump(mode="json") for q in quarantined],
    }


@router.get("/{run_id}/rejections.csv")
def get_run_rejections_csv(run_id: str, state: dict = Depends(get_owned_run)) -> Response:
    """Downloadable rejection file: the rejected rows + reasons, in CSV,
    CSV-injection-sanitized, so the user can fix and re-upload."""
    return Response(
        content=rejection_csv(state.get("quarantined", [])),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="rejections_{run_id}.csv"'},
    )


def _summarize(state) -> dict:
    return {
        "run_id": state["run_id"],
        "tenant_id": state["tenant_id"],
        "status": state["status"],
        "current_node": state.get("current_node"),
        "rows_accepted": len(state.get("rows", [])),
        "rows_quarantined": len(state.get("quarantined", [])),
        "quarantined": [q.model_dump(mode="json") for q in state.get("quarantined", [])],
        "errors": [e.model_dump(mode="json") for e in state.get("errors", [])],
    }
