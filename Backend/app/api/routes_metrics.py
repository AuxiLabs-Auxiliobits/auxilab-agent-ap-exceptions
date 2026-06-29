"""Dashboard metrics endpoints."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from app.api.deps import get_owned_run

router = APIRouter(prefix="/v1/runs", tags=["metrics"])

_CLOSED_CASE_STATUSES = frozenset({"RESOLVED", "WONT_FIX"})


@router.get("/{run_id}/metrics")
def get_metrics(run_id: str, state: dict = Depends(get_owned_run)) -> dict:
    metrics = state.get("metrics")
    queues = state.get("priority_queues")
    md = metrics.model_dump(mode="json") if metrics else None
    if md is not None:
        # Live, status-aware overlay: the pipeline metrics are a one-time snapshot
        # and don't know about resolution-tracker case updates, so fold the
        # current cases in at read time. Resolved/won't-fix invoices drop out of
        # the open and at-risk counts (evaluate_sla already excludes them).
        from app.comms.sla import evaluate_sla

        cases = state.get("cases", {}) or {}
        resolved = sum(
            1 for c in cases.values()
            if (c or {}).get("status") in _CLOSED_CASE_STATUSES
        )
        total = md.get("total_exceptions") or len(state.get("rows", []))
        sla = evaluate_sla(state, now=datetime.now(UTC), exclude_closed=True)
        md.update(
            {
                "resolved_count": resolved,
                "open_count": max(total - resolved, 0),
                "sla_at_risk_count": sla["breached"] + sla["due_soon"],
            }
        )
    return {
        "run_id": run_id,
        "metrics": md,
        "priority_queues": queues.model_dump(mode="json") if queues else None,
    }
