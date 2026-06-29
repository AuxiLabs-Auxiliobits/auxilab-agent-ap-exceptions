"""Severity validator — deterministic.

Authoritative severity assignment. The AI's suggestion is retained in
`severity_ai_suggested` for drift monitoring; this node sets `severity`.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from app.audit.logger import make_event
from app.config import get_settings
from app.graph.state import RunState
from app.schemas import (
    AuditEventType,
    ClassificationResult,
    ExceptionRow,
    Severity,
)

log = logging.getLogger("ap_agent.severity")


def compute_severity(amount: Decimal, days: int) -> Severity:
    s = get_settings()
    if float(amount) > s.severity_high_amount or days > s.severity_high_days:
        return Severity.HIGH
    if float(amount) >= s.severity_medium_amount_min:
        return Severity.MEDIUM
    return Severity.LOW


def severity_validator(state: RunState) -> RunState:
    from app.graph._logging import step_log

    rows: list[ExceptionRow] = list(state.get("rows", []))
    classifications: list[ClassificationResult] = list(state.get("classifications", []))
    audit = list(state.get("audit_events", []))

    with step_log("severity_validator", state) as info:
        row_by_id = {r.invoice_id: r for r in rows}
        new_classifications: list[ClassificationResult] = []
        drift = 0
        counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}

        for c in classifications:
            row = row_by_id.get(c.invoice_id)
            if row is None:
                new_classifications.append(c)
                continue
            canonical = compute_severity(row.invoice_amount, row.days_outstanding)
            if canonical != c.severity_ai_suggested:
                drift += 1
                log.debug(
                    "severity: drift invoice=%s ai=%s canonical=%s amount=%s days=%d",
                    c.invoice_id,
                    c.severity_ai_suggested.value,
                    canonical.value,
                    row.invoice_amount,
                    row.days_outstanding,
                )
            counts[canonical.value] += 1
            new_classifications.append(c.model_copy(update={"severity": canonical}))

        log.info(
            "severity: HIGH=%d MEDIUM=%d LOW=%d drift_vs_ai=%d",
            counts["HIGH"],
            counts["MEDIUM"],
            counts["LOW"],
            drift,
        )

        audit.append(
            make_event(
                run_id=state["run_id"],
                node_name="severity_validator",
                event_type=AuditEventType.NODE_END,
                metadata={"drift_count": drift, "total": len(classifications)},
            )
        )

        info["high"] = counts["HIGH"]
        info["medium"] = counts["MEDIUM"]
        info["low"] = counts["LOW"]
        info["drift"] = drift

    out = dict(state)
    out["classifications"] = new_classifications
    out["audit_events"] = audit
    out["current_node"] = "severity_validator"
    return out
