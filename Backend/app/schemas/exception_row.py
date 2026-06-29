"""ExceptionRow — normalized input row from the ERP exception queue."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ExceptionRow(BaseModel):
    """A single normalized exception row.

    Immutable. Validated at ingestion time.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    invoice_id: str = Field(min_length=1, max_length=64)
    vendor_name: str = Field(min_length=1, max_length=256)
    invoice_amount: Decimal = Field(ge=0)
    po_number: str | None = None
    exception_type: str = Field(min_length=1, max_length=64)
    exception_description: str = Field(min_length=1, max_length=2000)
    days_outstanding: int = Field(ge=0)
    approver_assigned: str | None = None
    # Optional per-invoice SLA window in days, sourced from the CSV. When present
    # it drives the SLA clock (deadline = received + sla_days) and overrides the
    # routing rule's sla_hours; when absent the rule's SLA applies.
    sla_days: int | None = Field(default=None, ge=0)


class QuarantinedRow(BaseModel):
    """A row that failed ingestion validation."""

    model_config = ConfigDict(extra="forbid")

    row_index: int
    raw: dict
    reason_code: str
    reason: str
