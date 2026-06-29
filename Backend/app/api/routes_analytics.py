"""Cross-run trend analytics — GET /v1/analytics/trends.

Surfaces how the operation trends across runs: volume, value, resolution rate,
and (from the case lifecycle) average time-to-resolve. Tenant-scoped, best-effort
over whatever runs the store currently holds. Runs without computed metrics
(in-progress / ingest failures) are skipped.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends

from app.api.auth import Principal, require_auth
from app.api.store import get_store

router = APIRouter(prefix="/v1/analytics", tags=["analytics"])

_CLOSED = {"RESOLVED", "WONT_FIX"}


def _parse_dt(v: object) -> datetime | None:
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


@router.get("/trends")
def get_trends(principal: Principal = Depends(require_auth)) -> dict:
    store = get_store()
    runs: list[dict] = []
    all_cycle_hours: list[float] = []

    for rid in store.list_ids():
        state = store.get(rid)
        if state is None:
            continue
        # Tenant scoping (the dev principal sees all, matching list_runs()).
        if principal.subject != "dev" and state.get("tenant_id") != principal.tenant_id:
            continue
        m = state.get("metrics")
        if m is None:
            continue

        run_created = _parse_dt(state.get("created_at"))
        cases = state.get("cases", {}) or {}
        resolved = 0
        closed = 0
        run_cycle: list[float] = []
        for c in cases.values():
            st = c.get("status")
            if st in _CLOSED:
                closed += 1
                if st == "RESOLVED":
                    resolved += 1
                cu = _parse_dt(c.get("updated_at"))
                if cu and run_created:
                    hours = (cu - run_created).total_seconds() / 3600.0
                    if hours >= 0:
                        run_cycle.append(hours)
        all_cycle_hours.extend(run_cycle)

        runs.append(
            {
                "run_id": state["run_id"],
                "created_at": run_created.isoformat() if run_created else None,
                "status": state.get("status"),
                "total_exceptions": m.total_exceptions,
                "total_value": str(m.total_exception_value),
                "auto_resolvable": m.auto_resolvable_count,
                "escalations": m.escalations_required,
                "high_severity": m.breakdown_by_severity.get("HIGH", 0),
                "avg_confidence": round(m.average_confidence, 4),
                "sla_at_risk": m.sla_at_risk_count,
                "resolved": resolved,
                "closed": closed,
                "avg_cycle_hours": round(sum(run_cycle) / len(run_cycle), 2) if run_cycle else None,
            }
        )

    # Oldest first, so a time series charts left → right.
    runs.sort(key=lambda r: r["created_at"] or "")

    total_ex = sum(r["total_exceptions"] for r in runs)
    total_val = sum((Decimal(r["total_value"]) for r in runs), Decimal(0))
    total_resolved = sum(r["resolved"] for r in runs)
    total_closed = sum(r["closed"] for r in runs)
    total_auto = sum(r["auto_resolvable"] for r in runs)
    conf_weighted = sum(r["avg_confidence"] * r["total_exceptions"] for r in runs)

    totals = {
        "runs": len(runs),
        "total_exceptions": total_ex,
        "total_value": str(total_val),
        "resolved": total_resolved,
        "closed": total_closed,
        "resolution_rate": round(total_closed / total_ex, 4) if total_ex else 0.0,
        "auto_resolution_rate": round(total_auto / total_ex, 4) if total_ex else 0.0,
        "avg_confidence": round(conf_weighted / total_ex, 4) if total_ex else 0.0,
        "avg_cycle_hours": round(sum(all_cycle_hours) / len(all_cycle_hours), 2)
        if all_cycle_hours
        else None,
    }
    return {"runs": runs, "totals": totals}
