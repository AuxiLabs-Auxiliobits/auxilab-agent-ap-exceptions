"""Operator SLA visibility + notifications (F1-2).

  GET  /v1/runs/{run_id}/sla     SLA status for a run (counts + breached/due-soon)
  POST /v1/runs/{run_id}/notify  send the AP team an operator SLA digest

These surface "what's waiting / breaching its SLA" to the AP *team* — distinct
from the vendor/internal invoice comms in routes_comms. Both are tenant-scoped.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, Depends

from app.api.auth import Principal
from app.api.deps import get_owned_run, require_permission
from app.api.org_config import resolve_settings
from app.api.roles import COMMS_SEND, RUN_READ
from app.comms import operator_notify
from app.comms.sla import evaluate_sla
from app.config import get_settings

log = logging.getLogger("ap_agent.routes_notifications")

router = APIRouter(prefix="/v1/runs", tags=["notifications"])


@router.get("/{run_id}/sla")
def run_sla(
    run_id: str,
    _owned: dict = Depends(get_owned_run),
    principal: Principal = Depends(require_permission(RUN_READ)),
) -> dict:
    """SLA status for the run: counts + the breached / due-soon item lists."""
    due = get_settings().comms_sla_due_soon_hours
    report = evaluate_sla(_owned, now=datetime.now(UTC), due_soon_hours=due)
    return {"run_id": run_id, **report}


@router.post("/{run_id}/notify")
def run_notify(
    run_id: str,
    body: dict[str, Any] | None = Body(default=None),
    _owned: dict = Depends(get_owned_run),
    principal: Principal = Depends(require_permission(COMMS_SEND)),
) -> dict:
    """Send the AP team an operator SLA digest for this run (dry-run by default,
    per COMMS_DRYRUN). Uses the caller org's resolved comms settings (BYOK)."""
    settings = resolve_settings(_owned.get("tenant_id") or "default")
    report = evaluate_sla(
        _owned, now=datetime.now(UTC), due_soon_hours=settings.comms_sla_due_soon_hours
    )

    # Fold in the human resolution lifecycle so the digest is a true reviewer
    # summary, not just an SLA list. "Needs follow-up" = breached AND not closed.
    cases = _owned.get("cases", {}) or {}
    closed_ids = {inv for inv, c in cases.items() if c.get("status") in ("RESOLVED", "WONT_FIX")}
    in_progress = sum(1 for c in cases.values() if c.get("status") == "IN_PROGRESS")
    needs_follow_up = sum(1 for i in report["breached_items"] if i["invoice_id"] not in closed_ids)
    report["cases"] = {
        "in_progress": in_progress,
        "resolved": len(closed_ids),
        "needs_follow_up": needs_follow_up,
    }

    result = operator_notify.send_sla_digest(run_id=run_id, report=report, settings=settings)
    return {
        "run_id": run_id,
        "notification": result,
        "summary": {
            "total_open": report["total_open"],
            "high_waiting": report["high_waiting"],
            "breached": report["breached"],
            "due_soon": report["due_soon"],
            "in_progress": in_progress,
            "resolved": len(closed_ids),
            "needs_follow_up": needs_follow_up,
        },
    }
