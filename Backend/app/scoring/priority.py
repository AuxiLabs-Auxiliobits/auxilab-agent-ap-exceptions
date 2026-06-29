"""Deterministic priority scoring engine.

priority_score =
    w_amount   * normalize(invoice_amount, 0, 100_000)
  + w_age      * normalize(days_outstanding, 0, 60)
  + w_severity * severity_weight(severity)
  + w_path     * path_weight(resolution_path)
  + w_conf     * (1 - confidence_score)
"""
from __future__ import annotations

from decimal import Decimal

from app.config import Settings
from app.schemas import (
    ClassificationResult,
    DashboardMetrics,
    ExceptionRow,
    PriorityBucket,
    PriorityEntry,
    PriorityQueues,
    ResolutionDecision,
    ResolutionPath,
    Severity,
)

_AMOUNT_CAP = 100_000.0
_AGE_CAP = 60.0

_SEVERITY_WEIGHT = {
    Severity.HIGH: 1.0,
    Severity.MEDIUM: 0.5,
    Severity.LOW: 0.1,
}

_PATH_WEIGHT = {
    ResolutionPath.ESCALATE_CONTROLLER: 1.0,
    ResolutionPath.HOLD_INVESTIGATION: 0.9,
    ResolutionPath.VENDOR_VALIDATION_REVIEW: 0.7,
    ResolutionPath.REQUEST_PO: 0.6,
    ResolutionPath.REQUEST_GRN: 0.6,
    ResolutionPath.MANUAL_REVIEW: 0.5,
    ResolutionPath.AUTO_APPROVE: 0.1,
}


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def score_row(
    row: ExceptionRow,
    classification: ClassificationResult,
    resolution: ResolutionDecision,
    settings: Settings,
) -> PriorityEntry:
    amount = float(row.invoice_amount)
    days = row.days_outstanding

    amount_n = _clip01(amount / _AMOUNT_CAP)
    age_n = _clip01(days / _AGE_CAP)
    sev_n = _SEVERITY_WEIGHT[classification.severity]
    path_n = _PATH_WEIGHT[resolution.resolution_path]
    conf_inv = 1.0 - classification.confidence_score

    score = (
        settings.w_amount * amount_n
        + settings.w_age * age_n
        + settings.w_severity * sev_n
        + settings.w_path * path_n
        + settings.w_conf * conf_inv
    )
    score = _clip01(score)

    if score >= settings.high_threshold or classification.severity == Severity.HIGH:
        bucket = PriorityBucket.HIGH
    elif score >= settings.medium_threshold:
        bucket = PriorityBucket.MEDIUM
    else:
        bucket = PriorityBucket.LOW

    drivers: list[str] = []
    if amount_n > 0.5:
        drivers.append(f"high_amount={amount}")
    if age_n > 0.5:
        drivers.append(f"aged={days}d")
    if classification.severity == Severity.HIGH:
        drivers.append("severity=HIGH")
    if resolution.resolution_path == ResolutionPath.ESCALATE_CONTROLLER:
        drivers.append("path=ESCALATE_CONTROLLER")
    if classification.confidence_score < 0.7:
        drivers.append(f"low_confidence={classification.confidence_score:.2f}")

    return PriorityEntry(
        invoice_id=row.invoice_id,
        priority_score=round(score, 4),
        bucket=bucket,
        drivers=drivers,
    )


def _tiebreak_key(
    entry: PriorityEntry,
    row_lookup: dict[str, ExceptionRow],
) -> tuple:
    row = row_lookup[entry.invoice_id]
    # Sort descending by score, then days_outstanding, then amount, then id asc.
    return (
        -entry.priority_score,
        -row.days_outstanding,
        -float(row.invoice_amount),
        entry.invoice_id,
    )


def build_queues_and_metrics(
    rows: list[ExceptionRow],
    classifications: list[ClassificationResult],
    resolutions: list[ResolutionDecision],
    settings: Settings,
) -> tuple[PriorityQueues, DashboardMetrics]:
    row_lookup = {r.invoice_id: r for r in rows}
    c_lookup = {c.invoice_id: c for c in classifications}
    r_lookup = {d.invoice_id: d for d in resolutions}

    entries: list[PriorityEntry] = []
    for row in rows:
        c = c_lookup.get(row.invoice_id)
        r = r_lookup.get(row.invoice_id)
        if not c or not r:
            continue
        entries.append(score_row(row, c, r, settings))

    entries.sort(key=lambda e: _tiebreak_key(e, row_lookup))

    queues = PriorityQueues(
        high=[e for e in entries if e.bucket == PriorityBucket.HIGH],
        medium=[e for e in entries if e.bucket == PriorityBucket.MEDIUM],
        low=[e for e in entries if e.bucket == PriorityBucket.LOW],
    )

    # Aggregates
    total = len(rows)
    auto_count = sum(
        1 for d in resolutions if d.resolution_path == ResolutionPath.AUTO_APPROVE
    )
    escalations = sum(
        1
        for d in resolutions
        if d.resolution_path
        in (ResolutionPath.ESCALATE_CONTROLLER, ResolutionPath.HOLD_INVESTIGATION)
    )
    total_value = sum((r.invoice_amount for r in rows), Decimal("0"))

    by_type: dict[str, int] = {}
    by_sev: dict[str, int] = {}
    by_path: dict[str, int] = {}
    for c in classifications:
        by_type[c.primary_exception_type.value] = (
            by_type.get(c.primary_exception_type.value, 0) + 1
        )
        by_sev[c.severity.value] = by_sev.get(c.severity.value, 0) + 1
    for d in resolutions:
        by_path[d.resolution_path.value] = by_path.get(d.resolution_path.value, 0) + 1

    sla_at_risk = sum(
        1
        for d in resolutions
        if row_lookup[d.invoice_id].days_outstanding * 24 >= d.sla_hours
    )

    avg_conf = (
        sum(c.confidence_score for c in classifications) / len(classifications)
        if classifications
        else 0.0
    )

    metrics = DashboardMetrics(
        total_exceptions=total,
        auto_resolvable_count=auto_count,
        escalations_required=escalations,
        total_exception_value=total_value,
        breakdown_by_type=by_type,
        breakdown_by_severity=by_sev,
        breakdown_by_resolution_path=by_path,
        top_5_actionable=entries[:5],
        sla_at_risk_count=sla_at_risk,
        average_confidence=round(avg_conf, 4),
    )

    return queues, metrics
