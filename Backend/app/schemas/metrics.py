"""Dashboard metrics schema."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.schemas.priority import PriorityEntry


class DashboardMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_exceptions: int
    auto_resolvable_count: int
    escalations_required: int
    total_exception_value: Decimal
    breakdown_by_type: dict[str, int]
    breakdown_by_severity: dict[str, int]
    breakdown_by_resolution_path: dict[str, int]
    top_5_actionable: list[PriorityEntry]
    sla_at_risk_count: int
    average_confidence: float
