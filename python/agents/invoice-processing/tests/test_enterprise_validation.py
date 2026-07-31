"""
Enterprise Validation Test Suite
tests/test_enterprise_validation.py

Tests all production-hardening features added in v3.0:
  1. Dependency-aware exception evaluation (missing field → skip dependent rule)
  2. Rule priority / short-circuiting (stop_further_checks)
  3. Age-based priority scoring (three age bands)
  4. Auto-resolution path
  5. SLA aggregation (MIN of all exception SLAs)
  6. Valid invoice routing (through QueueFormatter)

All tests run WITHOUT any LLM calls.
"""

import pytest
from datetime import datetime, timedelta

from invoice_processing.core.resolution_router import ResolutionRouter, InvoiceResult
from invoice_processing.core.exception_classifier import ExceptionClassification
from invoice_processing.core.queue_formatter import QueueFormatter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_router = ResolutionRouter()
_formatter = QueueFormatter()


def _exc(invoice_id: str, primary_type: str, evidence: str = "ERP evidence") -> ExceptionClassification:
    """Build a mock ExceptionClassification."""
    e = ExceptionClassification()
    e.invoice_id = invoice_id
    e.primary_type = primary_type
    e.evidence_used = evidence
    e.evidence_checked = "test"
    e.missing_data = []
    e.root_cause_hypothesis = f"Test hypothesis for {primary_type}"
    e.recommended_action = "Test action"
    e.business_rule_triggered = f"Rule: {primary_type}"
    e.success = True
    return e


def _raw(
    invoice_id: str,
    *,
    invoice_number: str = "INV-001",
    invoice_date: str = None,
    vendor_name: str = "Test Vendor Ltd",
    po_number: str = "PO-001",
    invoice_amount: str = "1000.00",
    currency: str = "USD",
) -> dict:
    """Build a minimal raw invoice dict."""
    if invoice_date is None:
        invoice_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    return {
        "invoice_id": invoice_id,
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "vendor_name": vendor_name,
        "po_number": po_number,
        "invoice_amount": invoice_amount,
        "currency": currency,
    }


def _run(raw_list, exc_list):
    """Convenience wrapper."""
    return _router.assign_batch(raw_list, exc_list)


def _types(result: InvoiceResult) -> list[str]:
    return [e.primary_type for e in result.evaluated_exceptions]


def _trace_contains(result: InvoiceResult, fragment: str) -> bool:
    return any(fragment in t for t in result.decision_trace)


# ===========================================================================
# 1. Dependency-Aware Exception Evaluation
# ===========================================================================

class TestDependencyAwareEvaluation:

    def test_missing_currency_skips_currency_mismatch(self):
        """
        When invoice currency is blank, Currency Mismatch must not be evaluated.
        Missing Required Data must still be raised.
        Trace must record the skip reason.
        """
        raw = _raw("D001", currency="")
        exc_missing = _exc("D001", "Missing Required Data")
        exc_currency = _exc("D001", "Currency Mismatch")

        results = _run([raw], [exc_missing, exc_currency])
        assert len(results) == 1
        r = results[0]

        assert "Missing Required Data" in _types(r)
        assert "Currency Mismatch" not in _types(r)
        assert _trace_contains(r, "Skipped Currency Mismatch evaluation because required field 'currency' is missing.")

    def test_missing_po_skips_all_po_dependent_rules(self):
        """
        When po_number is blank, PO Not Found, GRN Not Received,
        Amount Exceeds Tolerance, and Currency Mismatch must all be skipped.
        """
        raw = _raw("D002", po_number="")
        excs = [
            _exc("D002", "Missing Required Data"),
            _exc("D002", "PO Not Found"),
            _exc("D002", "GRN Not Received"),
            _exc("D002", "Amount Exceeds Tolerance"),
            _exc("D002", "Currency Mismatch"),
        ]

        results = _run([raw], excs)
        assert len(results) == 1
        r = results[0]

        assert "Missing Required Data" in _types(r)
        for skipped in ("PO Not Found", "GRN Not Received", "Amount Exceeds Tolerance", "Currency Mismatch"):
            assert skipped not in _types(r), f"{skipped} should have been skipped"
        assert _trace_contains(r, "Skipped PO Not Found evaluation because required field 'po_number' is missing.")

    def test_missing_invoice_number_skips_duplicate_checks(self):
        """
        When invoice_number is blank, both Exact and Potential Duplicate
        invoice checks must be skipped.
        """
        raw = _raw("D003", invoice_number="")
        excs = [
            _exc("D003", "Missing Required Data"),
            _exc("D003", "Exact Duplicate Invoice"),
            _exc("D003", "Potential Duplicate Invoice"),
        ]

        results = _run([raw], excs)
        assert len(results) == 1
        r = results[0]

        assert "Missing Required Data" in _types(r)
        assert "Exact Duplicate Invoice" not in _types(r)
        assert "Potential Duplicate Invoice" not in _types(r)
        assert _trace_contains(r, "Skipped Exact Duplicate Invoice evaluation because required field 'invoice_number' is missing.")


# ===========================================================================
# 2. Rule Priority / Short-Circuit
# ===========================================================================

class TestShortCircuit:

    def test_exact_duplicate_stops_further_checks(self):
        """
        Once Exact Duplicate Invoice is confirmed, remaining exceptions
        must not be evaluated and the trace must record the short-circuit reason.
        """
        raw = _raw("SC001")
        excs = [
            _exc("SC001", "Exact Duplicate Invoice"),
            _exc("SC001", "Amount Exceeds Tolerance"),
            _exc("SC001", "Currency Mismatch"),
        ]

        results = _run([raw], excs)
        assert len(results) == 1
        r = results[0]

        # Exact Duplicate should be in the evaluated exceptions list, alongside the others
        assert "Exact Duplicate Invoice" in _types(r)
        assert "Amount Exceeds Tolerance" in _types(r)
        assert "Currency Mismatch" in _types(r)

        # But the others must be in skipped_exceptions_trace
        skipped_rules = [s["skipped_rule"] for s in r.skipped_exceptions_trace]
        assert "Amount Exceeds Tolerance" in skipped_rules
        assert "Currency Mismatch" in skipped_rules

        # Trace must contain the stop_further_checks message
        assert _trace_contains(r, "stop_further_checks=true")
        assert _trace_contains(r, "skip routing")

    def test_non_stop_exception_does_not_short_circuit(self):
        """
        Currency Mismatch does NOT have stop_further_checks=true,
        so subsequent exceptions should still be evaluated.
        """
        raw = _raw("SC002")
        excs = [
            _exc("SC002", "Currency Mismatch"),
            _exc("SC002", "Vendor Mismatch"),
        ]

        results = _run([raw], excs)
        assert len(results) == 1
        r = results[0]

        # Both should be present
        assert "Currency Mismatch" in _types(r)
        assert "Vendor Mismatch" in _types(r)


# ===========================================================================
# 3. Age-Based Priority Scoring
# ===========================================================================

class TestAgePriorityScoring:
    """
    Base invoice: amount=$1000 (low_value=10), 1 exception (no extra count score).
    Age weights: recent=5, over_7_days=15, over_30_days=30.
    Currency Mismatch severity = Medium (50).
    Expected scores: 50+10+age_score = 60+age.
    """

    def test_recent_invoice_age_score_5(self):
        """0–7 days → Age Weight = 5 points."""
        invoice_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        raw = _raw("A001", invoice_date=invoice_date, invoice_amount="1000.00")
        exc = _exc("A001", "Currency Mismatch")

        results = _run([raw], [exc])
        r = results[0]

        assert _trace_contains(r, "Age Weight Applied: 5 points")
        assert r.raw_priority_score == 65.0  # Medium(50) + low_value(10) + recent(5)

    def test_medium_age_invoice_age_score_15(self):
        """8–30 days → Age Weight = 15 points."""
        invoice_date = (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d")
        raw = _raw("A002", invoice_date=invoice_date, invoice_amount="1000.00")
        exc = _exc("A002", "Currency Mismatch")

        results = _run([raw], [exc])
        r = results[0]

        assert _trace_contains(r, "Age Weight Applied: 15 points")
        assert r.raw_priority_score == 75.0  # Medium(50) + low_value(10) + over_7_days(15)

    def test_old_invoice_age_score_30(self):
        """31+ days → Age Weight = 30 points."""
        invoice_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
        raw = _raw("A003", invoice_date=invoice_date, invoice_amount="1000.00")
        exc = _exc("A003", "Currency Mismatch")

        results = _run([raw], [exc])
        r = results[0]

        assert _trace_contains(r, "Age Weight Applied: 30 points")
        assert r.raw_priority_score == 90.0  # Medium(50) + low_value(10) + over_30_days(30)

    def test_age_affects_priority_ranking(self):
        """Older invoices must rank higher than recent ones with identical amounts/exceptions."""
        date_recent = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        date_old    = (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d")

        raw_recent = _raw("AR", invoice_date=date_recent, invoice_amount="1000.00")
        raw_old    = _raw("AO", invoice_date=date_old,    invoice_amount="1000.00")

        results = _run(
            [raw_recent, raw_old],
            [_exc("AR", "Currency Mismatch"), _exc("AO", "Currency Mismatch")],
        )
        scores = {r.invoice_id: r.raw_priority_score for r in results}
        assert scores["AO"] > scores["AR"]


# ===========================================================================
# 4. Auto-Resolution Path
# ===========================================================================

class TestAutoResolution:

    def test_missing_required_data_only_is_auto_resolved(self):
        """
        An invoice with only Missing Required Data (auto_resolvable=true)
        must be flagged auto_resolved=True.
        """
        raw = _raw("AR001")
        exc = _exc("AR001", "Missing Required Data")

        results = _run([raw], [exc])
        r = results[0]

        assert r.auto_resolved is True
        assert _trace_contains(r, "automatically resolved")

    def test_future_date_only_is_auto_resolved(self):
        """Future Date (auto_resolvable=true) → auto_resolved=True."""
        raw = _raw("AR002")
        exc = _exc("AR002", "Future Date")

        results = _run([raw], [exc])
        assert results[0].auto_resolved is True

    def test_standalone_exact_duplicate_is_auto_resolved(self):
        """
        An invoice with standalone Exact Duplicate Invoice 
        must bypass escalation and be flagged auto_resolved.
        """
        raw = _raw("AR003")
        exc = _exc("AR003", "Exact Duplicate Invoice")

        results = _run([raw], [exc])
        assert results[0].auto_resolved is True
        assert results[0].escalation_required is False
        assert results[0].payment_blocked is False

    def test_mixed_auto_and_manual_not_auto_resolved(self):
        """
        If ANY exception is not auto-resolvable, the invoice must NOT be
        marked auto_resolved.
        """
        raw = _raw("AR004")
        excs = [
            _exc("AR004", "Future Date"),         # auto_resolvable=true
            _exc("AR004", "Currency Mismatch"),   # auto_resolvable=false
        ]

        results = _run([raw], excs)
        assert results[0].auto_resolved is False


# ===========================================================================
# 5. SLA Aggregation
# ===========================================================================

class TestSLAAggregation:

    def test_sla_uses_minimum_of_all_exceptions(self):
        """
        Vendor Mismatch=48h, GRN Not Received=72h → invoice SLA = MIN = 48h.
        """
        raw = _raw("SLA001")
        excs = [
            _exc("SLA001", "Vendor Mismatch"),     # 48h
            _exc("SLA001", "GRN Not Received"),    # 72h
        ]

        results = _run([raw], excs)
        assert results[0].sla_hours == 48

    def test_exact_dup_sla_is_24_hours(self):
        """Exact Duplicate Invoice alone → SLA = 24h (the tightest SLA)."""
        raw = _raw("SLA002")
        exc = _exc("SLA002", "Exact Duplicate Invoice")

        results = _run([raw], [exc])
        assert results[0].sla_hours == 24

    def test_three_exception_sla_takes_minimum(self):
        """
        Currency Mismatch=48h, Vendor Mismatch=48h, GRN Not Received=72h
        → SLA = MIN = 48h.
        """
        raw = _raw("SLA003")
        excs = [
            _exc("SLA003", "Currency Mismatch"),   # 48h
            _exc("SLA003", "Vendor Mismatch"),     # 48h
            _exc("SLA003", "GRN Not Received"),    # 72h
        ]

        results = _run([raw], excs)
        assert results[0].sla_hours == 48


# ===========================================================================
# 6. Valid Invoice Routing (QueueFormatter level)
# ===========================================================================

class TestValidInvoiceRouting:

    def test_valid_invoices_reported_in_dashboard(self):
        """
        Valid invoices passed to QueueFormatter must appear in dashboard
        valid_invoices_count and business_value_metrics.valid_invoice_value.
        """
        raw_v001 = _raw("V001", invoice_amount="1500.0")
        raw_v002 = _raw("V002", invoice_amount="950.0")

        results = _run([raw_v001, raw_v002], [])
        result = _formatter.build(results)
        dashboard = result["dashboard"]

        assert dashboard["valid_invoices_count"] == 2
        assert dashboard["business_value_metrics"]["valid_invoice_value"] == 2450.0

    def test_valid_invoice_queue_csv_is_written(self, tmp_path, monkeypatch):
        """
        valid_invoice_queue.csv must exist in the output directory and
        contain the correct invoice IDs.
        """
        import invoice_processing.core.queue_formatter as qf_module
        monkeypatch.setattr(qf_module, "_OUTPUT_DIR", tmp_path)

        raw = _raw("V010", invoice_amount="800.0")
        results = _run([raw], [])

        result = _formatter.build(results)
        out_dir = next(tmp_path.iterdir())  # timestamped run dir
        csv_path = out_dir / "valid_invoice_queue.csv"

        assert csv_path.exists(), "valid_invoice_queue.csv was not written"
        content = csv_path.read_text(encoding="utf-8")
        assert "V010" in content

    def test_exception_invoice_queue_csv_is_written(self, tmp_path, monkeypatch):
        """
        exception_invoice_queue.csv must exist and contain the exception invoice IDs.
        """
        import invoice_processing.core.queue_formatter as qf_module
        monkeypatch.setattr(qf_module, "_OUTPUT_DIR", tmp_path)

        # Create a minimal InvoiceResult via the router
        raw = _raw("E010")
        exc = _exc("E010", "Vendor Mismatch")
        invoices_results = _router.assign_batch([raw], [exc])

        result = _formatter.build(invoices_results)
        out_dir = next(tmp_path.iterdir())
        csv_path = out_dir / "exception_invoice_queue.csv"

        assert csv_path.exists(), "exception_invoice_queue.csv was not written"
        content = csv_path.read_text(encoding="utf-8")
        assert "E010" in content
