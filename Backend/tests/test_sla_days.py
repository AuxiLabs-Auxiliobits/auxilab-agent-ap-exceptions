"""Per-invoice CSV sla_days drives the SLA clock and overrides the rule SLA."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal


def _row(inv, *, sla_days=None):
    from app.schemas import ExceptionRow

    return ExceptionRow(
        invoice_id=inv, vendor_name="Acme", invoice_amount=Decimal("1000"),
        po_number="PO", exception_type="Price Variance", exception_description="d",
        days_outstanding=0, sla_days=sla_days,
    )


def _res(inv, sla_hours):
    from app.schemas import ResolutionDecision, ResolutionPath

    return ResolutionDecision(
        invoice_id=inv, resolution_path=ResolutionPath.ESCALATE_CONTROLLER,
        rule_id="r", rule_version="v1", rule_trace=["t"],
        requires_communication=True, sla_hours=sla_hours,
    )


def _state(row, res):
    from app.graph.builder import initial_state

    s = initial_state("run_slad", "default")
    s["created_at"] = datetime.now(UTC) - timedelta(hours=30)  # 30h since received
    s["rows"] = [row]
    s["resolutions"] = [res]
    s["cases"] = {}
    return s


def test_sla_days_overrides_rule_sla_hours():
    from app.comms.sla import evaluate_sla

    now = datetime.now(UTC)
    # Rule says 8h → deadline 22h ago → breached.
    rule_only = evaluate_sla(_state(_row("INV-1"), _res("INV-1", 8)), now=now)
    assert rule_only["breached"] == 1

    # Same invoice but CSV sla_days=2 (48h) → deadline 18h in the future → on track.
    with_csv = evaluate_sla(_state(_row("INV-1", sla_days=2), _res("INV-1", 8)), now=now)
    assert with_csv["breached"] == 0
    assert with_csv["due_soon"] == 0


def test_ingest_parses_sla_days_and_blank_is_none():
    from app.upload_format import prepare_model_row

    assert prepare_model_row({"sla_days": "5", "days_outstanding": "3"})["sla_days"] == 5
    # Blank / missing → key dropped so ExceptionRow's default (None) applies.
    assert "sla_days" not in prepare_model_row({"sla_days": "", "days_outstanding": "3"})
    assert "sla_days" not in prepare_model_row({"days_outstanding": "3"})
