"""Vendor reliability profile schemas.

Each profile is a longitudinal record of one vendor's exception history.
Profiles are passed into the AI classifier as additional context — the
classifier can use a vendor's track record to disambiguate borderline
exceptions ("Oracle's historical variance is 0.8% ± 0.3% — this 8% is
genuinely anomalous").

The reliability_score is deterministic — computed from the observed
counts, not learned — so it's auditable and replayable.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class VendorProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vendor_name: str
    total_invoices_seen: int = 0
    total_amount_processed: Decimal = Decimal("0")
    exception_type_counts: dict[str, int] = Field(default_factory=dict)
    resolution_path_counts: dict[str, int] = Field(default_factory=dict)

    # Rolling averages (updated incrementally; not perfectly accurate after
    # the first few thousand observations, but cheap and good enough for
    # use as a soft signal to the LLM).
    average_variance_pct: float | None = None
    average_days_outstanding: float = 0.0
    average_confidence: float = 0.0

    duplicate_count: int = 0
    auto_approved_count: int = 0
    escalated_count: int = 0
    missing_po_count: int = 0
    unapproved_vendor_count: int = 0

    first_seen_at: datetime
    last_seen_at: datetime

    def reliability_score(self) -> float:
        """Deterministic score in [0, 1] — higher = more reliable.

        Heuristic, not learned. Tuned so that:
          - a vendor with 80% auto-approve rate scores ~0.75
          - a vendor with 50% duplicate rate scores ~0.20
          - a brand-new (unseen) vendor scores 0.50
        """
        n = self.total_invoices_seen
        if n == 0:
            return 0.5

        auto_rate = self.auto_approved_count / n
        escal_rate = self.escalated_count / n
        dup_rate = self.duplicate_count / n
        mpo_rate = self.missing_po_count / n
        uv_rate = self.unapproved_vendor_count / n

        score = (
            0.5
            + 0.30 * auto_rate
            - 0.20 * escal_rate
            - 0.30 * dup_rate
            - 0.10 * mpo_rate
            - 0.10 * uv_rate
        )
        return max(0.0, min(1.0, round(score, 3)))


class VendorProfileSnapshot(BaseModel):
    """Serializable view of all profiles — used by the GET /v1/vendors response."""

    model_config = ConfigDict(extra="forbid")

    profiles: list[VendorProfile]
    total_vendors: int
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC)
    )
