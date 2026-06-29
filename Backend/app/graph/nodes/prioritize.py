"""Prioritization node — deterministic."""
from __future__ import annotations

import logging

from app.audit.logger import make_event
from app.config import get_settings
from app.graph.state import RunState
from app.schemas import AuditEventType
from app.scoring.priority import build_queues_and_metrics

log = logging.getLogger("ap_agent.prioritize")


def prioritize_node(state: RunState) -> RunState:
    from app.graph._logging import step_log

    settings = get_settings()

    with step_log("prioritize_node", state) as info:
        queues, metrics = build_queues_and_metrics(
            list(state.get("rows", [])),
            list(state.get("classifications", [])),
            list(state.get("resolutions", [])),
            settings,
        )

        log.info(
            "prioritize: HIGH=%d MEDIUM=%d LOW=%d avg_conf=%.2f sla_at_risk=%d total_value=%s",
            len(queues.high),
            len(queues.medium),
            len(queues.low),
            metrics.average_confidence,
            metrics.sla_at_risk_count,
            metrics.total_exception_value,
        )
        for e in metrics.top_5_actionable:
            log.info(
                "prioritize: top → %s score=%.3f bucket=%s drivers=%s",
                e.invoice_id,
                e.priority_score,
                e.bucket.value,
                ",".join(e.drivers) or "-",
            )

        audit = list(state.get("audit_events", []))
        audit.append(
            make_event(
                run_id=state["run_id"],
                node_name="prioritize_node",
                event_type=AuditEventType.NODE_END,
                metadata={
                    "high": len(queues.high),
                    "medium": len(queues.medium),
                    "low": len(queues.low),
                    "avg_confidence": metrics.average_confidence,
                },
            )
        )

        info["high"] = len(queues.high)
        info["medium"] = len(queues.medium)
        info["low"] = len(queues.low)

    out = dict(state)
    out["priority_queues"] = queues
    out["metrics"] = metrics
    out["audit_events"] = audit
    out["current_node"] = "prioritize_node"
    return out
