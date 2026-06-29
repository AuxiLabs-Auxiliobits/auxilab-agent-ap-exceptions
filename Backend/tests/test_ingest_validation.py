"""Validation + column-mapping coverage for the ingest node and upload_format.

Run: python -m pytest tests/test_ingest_validation.py -q
"""
from __future__ import annotations

from app.graph.builder import initial_state
from app.graph.nodes.ingest import ingest_from_bytes
from app.schemas import RunStatus
from app.upload_format import (
    rejection_csv,
    resolve_columns,
    sanitize_csv_cell,
)

CANON_HEADER = (
    "invoice_id,vendor_name,invoice_amount,po_number,exception_type,"
    "exception_description,days_outstanding,approver_assigned\n"
)


def _ingest(csv_text: str, filename: str = "q.csv"):
    state = initial_state("run_test", "tenant_test")
    return ingest_from_bytes(state, content=csv_text.encode("utf-8"), filename=filename)


# --- positive ------------------------------------------------------------- #
def test_canonical_csv_accepts_all_rows():
    out = _ingest(CANON_HEADER + "INV-1,Oracle,100,PO-1,Price Variance,desc,5,jane\n")
    assert out["status"] != RunStatus.FAILED
    assert len(out["rows"]) == 1 and len(out["quarantined"]) == 0


def test_alias_headers_are_auto_mapped():
    # Different column names that all mean the canonical fields.
    text = (
        "Invoice No,Supplier,Amount,Issue,Description,Age\n"
        "INV-9,Acme Corp,1500,Missing PO,No PO on file,7\n"
    )
    out = _ingest(text)
    assert out["status"] != RunStatus.FAILED
    assert len(out["rows"]) == 1
    r = out["rows"][0]
    assert r.invoice_id == "INV-9" and r.vendor_name == "Acme Corp"
    assert str(r.invoice_amount) == "1500" and r.days_outstanding == 7


def test_optional_headers_can_be_omitted():
    # No po_number / approver_assigned columns at all → still accepted.
    text = (
        "invoice_id,vendor_name,invoice_amount,exception_type,exception_description,days_outstanding\n"
        "INV-2,Beta,200,Duplicate,dup,3\n"
    )
    out = _ingest(text)
    assert out["status"] != RunStatus.FAILED and len(out["rows"]) == 1
    assert out["rows"][0].po_number is None


def test_extra_columns_ignored():
    out = _ingest(
        CANON_HEADER.rstrip("\n") + ",legacy_id,notes\n"
        + "INV-3,Gamma,300,PO-3,Duplicate,d,4,jane,XYZ,whatever\n"
    )
    assert out["status"] != RunStatus.FAILED and len(out["rows"]) == 1


def test_invoice_date_derives_days_outstanding():
    text = (
        "invoice_id,vendor_name,invoice_amount,exception_type,exception_description,invoice_date\n"
        "INV-4,Delta,400,Missing PO,no po,2020-01-01\n"
    )
    out = _ingest(text)
    assert out["status"] != RunStatus.FAILED and len(out["rows"]) == 1
    assert out["rows"][0].days_outstanding > 0


def test_currency_formatting_tolerated():
    out = _ingest(CANON_HEADER + 'INV-5,Eps,"$1,234.50",PO-5,Duplicate,d,1,jane\n')
    assert len(out["rows"]) == 1
    assert str(out["rows"][0].invoice_amount) == "1234.50"


# --- file-level rejections ------------------------------------------------ #
def test_empty_file_fails():
    out = _ingest("")
    assert out["status"] == RunStatus.FAILED


def test_missing_required_column_fails():
    text = "invoice_id,vendor_name,exception_type,exception_description,days_outstanding\nINV-6,Z,Duplicate,d,1\n"
    out = _ingest(text)  # invoice_amount missing
    assert out["status"] == RunStatus.FAILED
    assert "Missing required" in out["errors"][-1].message


def test_duplicate_column_fails():
    text = (
        "invoice_id,invoice_id,vendor_name,invoice_amount,exception_type,exception_description,days_outstanding\n"
        "INV-7,INV-7,Z,100,Duplicate,d,1\n"
    )
    out = _ingest(text)
    assert out["status"] == RunStatus.FAILED
    assert "Duplicate column" in out["errors"][-1].message


# --- row-level quarantine ------------------------------------------------- #
def test_negative_amount_quarantined():
    out = _ingest(CANON_HEADER + "INV-8,Z,-50,PO-8,Duplicate,d,1,jane\n")
    assert len(out["rows"]) == 0 and len(out["quarantined"]) == 1
    assert out["quarantined"][0].reason_code == "NEGATIVE_AMOUNT"


def test_missing_value_quarantined():
    out = _ingest(CANON_HEADER + "INV-9,,100,PO-9,Duplicate,d,1,jane\n")  # blank vendor
    assert len(out["quarantined"]) == 1
    assert out["quarantined"][0].reason_code in ("MISSING_VALUE", "SCHEMA_VALIDATION")


def test_duplicate_invoice_id_quarantined():
    out = _ingest(
        CANON_HEADER
        + "INV-10,Z,100,PO,Duplicate,d,1,jane\n"
        + "INV-10,Z,200,PO,Duplicate,d,2,jane\n"
    )
    assert len(out["rows"]) == 1 and len(out["quarantined"]) == 1
    assert out["quarantined"][0].reason_code == "DUPLICATE_INVOICE_ID"


def test_future_date_quarantined():
    text = (
        "invoice_id,vendor_name,invoice_amount,exception_type,exception_description,invoice_date\n"
        "INV-11,Z,100,Duplicate,d,2999-01-01\n"
    )
    out = _ingest(text)
    assert len(out["quarantined"]) == 1 and out["quarantined"][0].reason_code == "FUTURE_DATE"


# --- helpers -------------------------------------------------------------- #
def test_resolve_columns_detects_alias_duplicates():
    rename, unknown, dups = resolve_columns(["Invoice No", "InvoiceNo", "Supplier"])
    assert "invoice_id" in dups  # both map to invoice_id


def test_csv_injection_is_sanitized():
    assert sanitize_csv_cell("=cmd|'/c calc'!A1").startswith("'=")
    assert sanitize_csv_cell("+1").startswith("'+")
    assert sanitize_csv_cell("normal") == "normal"


def test_rejection_csv_contains_reason_and_is_safe():
    out = _ingest(CANON_HEADER + "=danger,Z,-50,PO,Duplicate,d,1,jane\n")
    csv_text = rejection_csv(out["quarantined"])
    assert "reason_code" in csv_text and "NEGATIVE_AMOUNT" in csv_text
    assert "'=danger" in csv_text  # formula-injection neutralized
