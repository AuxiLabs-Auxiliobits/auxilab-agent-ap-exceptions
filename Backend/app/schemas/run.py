"""Run-level schemas."""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class RunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class NodeError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_name: str
    invoice_id: str | None = None
    error_class: str
    message: str
    timestamp: datetime
    attempt: int = 1
    is_retryable: bool = False


class RunSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    tenant_id: str
    status: RunStatus
    created_at: datetime
    rows_accepted: int
    rows_quarantined: int
    current_node: str | None = None
