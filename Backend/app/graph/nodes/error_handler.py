"""Error-handler node.

Records errors into the audit trail and decides whether to continue in
degraded mode (per-row failures) or mark the run failed (catastrophic
schema/parsing failures already short-circuited upstream).
"""
from __future__ import annotations

import logging

from app.audit.logger import make_event
from app.graph.state import RunState
from app.schemas import AuditEventType, RunStatus

log = logging.getLogger("ap_agent.error")


def error_handler(state: RunState) -> RunState:
    from app.graph._logging import step_log

    errors = list(state.get("errors", []))
    audit = list(state.get("audit_events", []))

    with step_log("error_handler", state) as info:
        log.warning(
            "error_handler: processing errors=%d incoming_status=%s",
            len(errors),
            state.get("status"),
        )
        for e in errors:
            log.warning(
                "error_handler: origin=%s invoice=%s class=%s retryable=%s msg=%s",
                e.node_name,
                e.invoice_id,
                e.error_class,
                e.is_retryable,
                e.message[:120],
            )
            audit.append(
                make_event(
                    run_id=state["run_id"],
                    node_name="error_handler",
                    event_type=AuditEventType.ERROR,
                    invoice_id=e.invoice_id,
                    metadata={
                        "origin_node": e.node_name,
                        "error_class": e.error_class,
                        "message": e.message[:200],
                        "is_retryable": e.is_retryable,
                    },
                )
            )

        info["errors"] = len(errors)

    out = dict(state)
    out["audit_events"] = audit
    if state.get("status") != RunStatus.FAILED:
        out["status"] = RunStatus.RUNNING  # degraded mode: keep going
    out["current_node"] = "error_handler"
    return out
