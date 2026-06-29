"""SLA evaluation over a run's resolutions (F1-2).

Pure and IO-free: given a run's state and the current time, classify each item's
resolution against its SLA deadline as ``ok`` / ``due_soon`` / ``breached``.

The SLA clock is anchored to when the invoice was **received** — approximated as
``run created_at − days_outstanding`` — so the deadline is ``received + sla_hours``.
This is the single, business-correct definition shared by the UI SLA cockpit, the
sidebar/header badges, and this operator digest: an invoice that arrived 10 days
ago with an 8h SLA is overdue regardless of when the batch was uploaded. (It was
previously anchored to run-start, which disagreed with the rest of the system.)
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any


def _as_aware(value: Any) -> datetime | None:
    """Coerce a stored timestamp (datetime or ISO string) to a UTC-aware dt."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


_CLOSED_CASE_STATUSES = frozenset({"RESOLVED", "WONT_FIX"})


def evaluate_sla(
    state: dict,
    *,
    now: datetime,
    due_soon_hours: float = 4.0,
    exclude_closed: bool = False,
) -> dict:
    """Build the operator SLA report for a run.

    Returns counts (total open, HIGH waiting, breached, due-soon) plus the
    breached/due-soon item lists (breached sorted most-overdue first).

    By default this reports the **raw** SLA state — a breached invoice counts as
    breached even after it's been resolved (the operator digest wants the raw
    breach count alongside a separate "needs follow-up" figure). Pass
    ``exclude_closed=True`` for the *actionable* view used by the dashboard and
    the assistant: a resolved/won't-fix case is then off the clock and drops out
    of open / breached / due-soon entirely."""
    created = _as_aware(state.get("created_at"))
    rows_by_id = {r.invoice_id: r for r in state.get("rows", [])}
    cases = state.get("cases", {}) or {}
    closed_ids = (
        {
            inv for inv, c in cases.items()
            if (c or {}).get("status") in _CLOSED_CASE_STATUSES
        }
        if exclude_closed
        else set()
    )
    sent_ids = {
        d.invoice_id
        for d in state.get("drafts", [])
        if getattr(d, "send_status", None) is not None
        and d.send_status.value in ("sent", "dryrun")
    }
    pq = state.get("priority_queues")
    high_ids = {e.invoice_id for e in pq.high} if pq is not None else set()

    items: list[dict] = []
    for res in state.get("resolutions", []):
        if res.invoice_id in closed_ids:
            continue  # resolved / won't-fix → off the clock
        row = rows_by_id.get(res.invoice_id)
        # Deadline = invoice-received time (run start − its age) + SLA window, so
        # this matches the UI cockpit and badges exactly. The SLA window comes
        # from the invoice's own sla_days (CSV) when present, otherwise the
        # routing rule's sla_hours.
        if created is not None:
            days = getattr(row, "days_outstanding", 0) or 0
            sla_days = getattr(row, "sla_days", None)
            window = (
                timedelta(days=sla_days)
                if sla_days is not None
                else timedelta(hours=res.sla_hours)
            )
            deadline = created - timedelta(days=days) + window
        else:
            deadline = None
        if deadline is None:
            status, overdue = "unknown", None
        elif now >= deadline:
            status = "breached"
            overdue = round((now - deadline).total_seconds() / 3600.0, 2)
        elif now >= deadline - timedelta(hours=due_soon_hours):
            status, overdue = "due_soon", None
        else:
            status, overdue = "ok", None
        items.append(
            {
                "invoice_id": res.invoice_id,
                "vendor_name": getattr(row, "vendor_name", None),
                "invoice_amount": float(row.invoice_amount) if row is not None else None,
                "resolution_path": res.resolution_path.value,
                "sla_hours": res.sla_hours,
                "deadline": deadline.isoformat() if deadline else None,
                "status": status,
                "hours_overdue": overdue,
                "comms_sent": res.invoice_id in sent_ids,
                "priority": "HIGH" if res.invoice_id in high_ids else None,
            }
        )

    breached = [i for i in items if i["status"] == "breached"]
    due_soon = [i for i in items if i["status"] == "due_soon"]
    breached.sort(key=lambda i: i["hours_overdue"] or 0.0, reverse=True)

    return {
        "generated_at": now.isoformat(),
        "total_open": len(items),
        "high_waiting": len(high_ids),
        "breached": len(breached),
        "due_soon": len(due_soon),
        "breached_items": breached,
        "due_soon_items": due_soon,
    }
