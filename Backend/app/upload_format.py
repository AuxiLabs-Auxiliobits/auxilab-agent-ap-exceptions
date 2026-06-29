"""Single source of truth for the accepted upload format.

Owns: the canonical column spec (required/optional + types), header-alias
resolution (smart column mapping), delimiter sniffing, CSV-injection
sanitization, the downloadable CSV template, the record-level rejection report,
and per-row preparation/coercion. Imported by the ingest node (validation) and
the API (format spec, template, rejection download) so both never drift.

Leaf module: depends only on stdlib + app.schemas (no graph/api imports).
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from app.schemas import ExceptionRow

# --------------------------------------------------------------------------- #
# Canonical column spec
# --------------------------------------------------------------------------- #
COLUMNS: list[dict[str, Any]] = [
    {"name": "invoice_id", "required": True, "type": "string",
     "description": "Unique invoice identifier (1–64 chars)."},
    {"name": "vendor_name", "required": True, "type": "string",
     "description": "Vendor / supplier name (1–256 chars)."},
    {"name": "invoice_amount", "required": True, "type": "decimal",
     "description": "Invoice gross amount, must be >= 0 (currency symbols/commas tolerated)."},
    {"name": "exception_type", "required": True, "type": "enum",
     "description": "Exception category (Price Variance, Missing PO, Duplicate, etc.)."},
    {"name": "exception_description", "required": True, "type": "string",
     "description": "Free-text reason (1–2000 chars)."},
    {"name": "days_outstanding", "required": False, "type": "integer",
     "description": "Age in days, >= 0. Required only if invoice_date is absent."},
    {"name": "invoice_date", "required": False, "type": "date",
     "description": "ISO-8601 date (YYYY-MM-DD); used to derive days_outstanding."},
    {"name": "po_number", "required": False, "type": "string",
     "description": "Purchase order number (optional)."},
    {"name": "approver_assigned", "required": False, "type": "string",
     "description": "Assigned approver name or email (optional)."},
    {"name": "sla_days", "required": False, "type": "integer",
     "description": "Per-invoice SLA window in days (>= 0). When present it drives "
                    "the SLA clock and overrides the routing rule's SLA."},
]

CANONICAL: set[str] = {c["name"] for c in COLUMNS}
# File-level required columns. invoice_date/days_outstanding form an either/or
# pair, validated separately so users can supply whichever they have.
CORE_REQUIRED: set[str] = {
    "invoice_id", "vendor_name", "invoice_amount", "exception_type", "exception_description",
}
DATE_COLUMNS: set[str] = {"days_outstanding", "invoice_date"}
MODEL_FIELDS: set[str] = set(ExceptionRow.model_fields.keys())
MAX_SIZE_MB = 25

# Normalized alias -> canonical column.
_ALIASES: dict[str, str] = {
    "invoiceno": "invoice_id", "invoicenumber": "invoice_id", "invnumber": "invoice_id",
    "invno": "invoice_id", "invoice": "invoice_id", "billno": "invoice_id",
    "documentno": "invoice_id", "docno": "invoice_id", "invoiceid": "invoice_id",
    "vendor": "vendor_name", "suppliername": "vendor_name", "supplier": "vendor_name",
    "payee": "vendor_name", "merchant": "vendor_name", "vendorname": "vendor_name",
    "amount": "invoice_amount", "invoicetotal": "invoice_amount", "total": "invoice_amount",
    "grossamount": "invoice_amount", "amt": "invoice_amount", "value": "invoice_amount",
    "invoiceamount": "invoice_amount",
    "date": "invoice_date", "invoicedt": "invoice_date", "billdate": "invoice_date",
    "postingdate": "invoice_date", "invoicedate": "invoice_date",
    "po": "po_number", "pono": "po_number", "purchaseorder": "po_number",
    "orderno": "po_number", "ponumber": "po_number",
    "exception": "exception_type", "issue": "exception_type", "issuetype": "exception_type",
    "errortype": "exception_type", "category": "exception_type", "exceptiontype": "exception_type",
    "description": "exception_description", "reason": "exception_description",
    "issuedescription": "exception_description", "exceptionreason": "exception_description",
    "exceptiondescription": "exception_description",
    "days": "days_outstanding", "age": "days_outstanding", "aging": "days_outstanding",
    "daysopen": "days_outstanding", "dpo": "days_outstanding", "overduedays": "days_outstanding",
    "daysoutstanding": "days_outstanding",
    "approver": "approver_assigned", "assignedto": "approver_assigned",
    "approvedby": "approver_assigned", "assignedapprover": "approver_assigned",
    "approverassigned": "approver_assigned",
    "sladays": "sla_days", "slaindays": "sla_days", "slatargetdays": "sla_days",
    "slawindowdays": "sla_days", "slabusinessdays": "sla_days",
}


def normalize_header(h: Any) -> str:
    """Lowercase + strip everything but [a-z0-9] so 'Invoice #', 'Inv_No',
    'invoice no' all collapse to a comparable key."""
    return re.sub(r"[^a-z0-9]", "", str(h).strip().lower())


# canonical-normalized form -> canonical, merged with aliases.
_RESOLVE: dict[str, str] = {normalize_header(c): c for c in CANONICAL}
_RESOLVE.update(_ALIASES)


def resolve_column(header: Any) -> str | None:
    """Map a raw header to its canonical name, or None if unrecognized."""
    return _RESOLVE.get(normalize_header(header))


def resolve_columns(headers: list[str]) -> tuple[dict[str, str], list[str], list[str]]:
    """Return (rename_map, unknown_headers, duplicate_canonicals).

    rename_map only includes headers whose canonical name differs from the
    original. duplicate_canonicals lists canonicals that >1 header maps to.
    """
    rename_map: dict[str, str] = {}
    seen: dict[str, int] = {}
    unknown: list[str] = []
    for h in headers:
        c = resolve_column(h)
        if c is None:
            unknown.append(h)
            continue
        if h != c:
            rename_map[h] = c
        seen[c] = seen.get(c, 0) + 1
    duplicates = sorted(k for k, n in seen.items() if n > 1)
    return rename_map, unknown, duplicates


def find_duplicate_columns(headers: list[str]) -> list[str]:
    """Canonical fields that appear more than once across the raw headers."""
    seen: dict[str, int] = {}
    for h in headers:
        c = resolve_column(h)
        if c is None:
            continue
        seen[c] = seen.get(c, 0) + 1
    return sorted(k for k, n in seen.items() if n > 1)


# --------------------------------------------------------------------------- #
# Delimiter / header sniffing
# --------------------------------------------------------------------------- #
def _sniff(line: str) -> str:
    if not line:
        return ","
    try:
        return csv.Sniffer().sniff(line, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def _first_line(content: bytes) -> str:
    try:
        text = content.decode("utf-8-sig", errors="replace")
    except Exception:  # noqa: BLE001
        return ""
    return next((ln for ln in text.splitlines() if ln.strip()), "")


def sniff_delimiter(content: bytes) -> str:
    return _sniff(_first_line(content))


def raw_csv_headers(content: bytes) -> list[str]:
    first = _first_line(content)
    if not first:
        return []
    return next(csv.reader([first], delimiter=_sniff(first)), [])


# --------------------------------------------------------------------------- #
# Per-row preparation / coercion
# --------------------------------------------------------------------------- #
class RowReject(Exception):  # noqa: N818 — domain term (a row is "rejected"), not an *Error
    """A business-rule rejection carrying a stable reason code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _to_decimal(s: Any) -> Decimal:
    t = str(s).strip()
    if t == "":
        return Decimal("0")
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()").replace(",", "").replace("$", "").replace(" ", "")
    val = Decimal(t)
    return -val if neg else val


def prepare_model_row(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce one (already canonical-renamed) record into ExceptionRow input.

    Derives days_outstanding from invoice_date when needed, rejects future
    dates, tolerates currency formatting, and drops unrecognized keys so
    ExceptionRow(extra='forbid') never trips on extra columns.
    """
    iso = str(raw.get("invoice_date", "") or "").strip()
    days_raw = str(raw.get("days_outstanding", "") or "").strip()

    out: dict[str, Any] = {k: raw[k] for k in MODEL_FIELDS if k in raw}

    if iso:
        try:
            d = date.fromisoformat(iso[:10])
        except ValueError:
            d = None
        if d is not None:
            if d > date.today():
                raise RowReject("FUTURE_DATE", f"invoice_date {iso} is in the future.")
            if not days_raw or days_raw.lower() in ("none", "nan"):
                out["days_outstanding"] = (date.today() - d).days

    out["invoice_amount"] = _to_decimal(out.get("invoice_amount", "0"))
    out["days_outstanding"] = int(float(str(out.get("days_outstanding", "0") or "0")))
    for k in ("po_number", "approver_assigned"):
        if str(out.get(k, "")).strip() in ("", "None", "nan"):
            out[k] = None
    # sla_days is optional: drop when blank so ExceptionRow's default (None)
    # applies; otherwise coerce to int (the rule SLA is used when it's absent).
    sla_raw = str(out.get("sla_days", "") or "").strip()
    if sla_raw == "" or sla_raw.lower() in ("none", "nan"):
        out.pop("sla_days", None)
    else:
        out["sla_days"] = int(float(sla_raw))
    return out


def friendly_reason(exc: Exception) -> tuple[str, str]:
    """Map a validation/coercion error to (reason_code, human message)."""
    if isinstance(exc, ValidationError):
        parts = []
        for e in exc.errors()[:5]:
            loc = ".".join(str(x) for x in e.get("loc", ())) or "field"
            parts.append(f"{loc}: {e.get('msg', 'invalid')}")
        joined = "; ".join(parts)
        low = joined.lower()
        if "invoice_amount" in low and "greater than or equal to 0" in low:
            return "NEGATIVE_AMOUNT", joined[:500]
        if "days_outstanding" in low and "greater than or equal to 0" in low:
            return "NEGATIVE_DAYS", joined[:500]
        if "too_short" in low or "at least 1" in low:
            return "MISSING_VALUE", joined[:500]
        return "SCHEMA_VALIDATION", joined[:500]
    if isinstance(exc, InvalidOperation):
        return "INVALID_NUMBER", "invoice_amount is not a valid number."
    return "INVALID_VALUE", str(exc)[:500]


# --------------------------------------------------------------------------- #
# CSV-injection-safe emit helpers
# --------------------------------------------------------------------------- #
_FORMULA_PREFIX = ("=", "+", "-", "@", "\t", "\r")


def sanitize_csv_cell(value: Any) -> str:
    """Neutralize spreadsheet formula injection when WE emit a CSV."""
    s = "" if value is None else str(value)
    if s and s[0] in _FORMULA_PREFIX:
        return "'" + s
    return s


_TEMPLATE_HEADER = [
    "invoice_id", "vendor_name", "invoice_amount", "invoice_date", "po_number",
    "exception_type", "exception_description", "days_outstanding", "approver_assigned",
]
_TEMPLATE_SAMPLE = [
    ["INV-2001", "Halford Logistics", "182400.00", "2026-04-15", "PO-99821",
     "Price Variance", "Unit price 14% over PO on 3 lines", "61", "controller@acme.com"],
    ["INV-2002", "Cedar Tooling Co.", "44950.00", "2026-05-02", "",
     "Missing PO", "No purchase order on file", "33", ""],
    ["INV-2003", "Brightpath Media", "9120.00", "2026-05-20", "PO-99710",
     "Duplicate", "Same vendor and amount as prior invoice INV-1845", "12", "ap.clerk@acme.com"],
]


def csv_template() -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(_TEMPLATE_HEADER)
    for row in _TEMPLATE_SAMPLE:
        w.writerow(row)
    return out.getvalue()


def rejection_csv(quarantined: list[Any]) -> str:
    """Build the downloadable rejection report: each rejected row, its reason,
    plus the original cells (CSV-injection-sanitized)."""
    raw_keys: list[str] = []
    for q in quarantined:
        for k in (q.raw or {}):
            if k not in raw_keys:
                raw_keys.append(str(k))
    header = ["row_index", "invoice_id", "reason_code", "reason", *raw_keys]
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(header)
    for q in quarantined:
        raw = q.raw or {}
        w.writerow([
            q.row_index,
            sanitize_csv_cell(raw.get("invoice_id", "")),
            q.reason_code,
            sanitize_csv_cell(q.reason),
            *[sanitize_csv_cell(raw.get(k, "")) for k in raw_keys],
        ])
    return out.getvalue()


def format_spec() -> dict[str, Any]:
    """Machine-readable description of the accepted import format (for the UI)."""
    return {
        "accepted_file_types": [".csv", ".json"],
        "max_size_mb": MAX_SIZE_MB,
        "delimiters_supported": [",", ";", "tab", "|"],
        "columns": COLUMNS,
        "notes": [
            "Provide either days_outstanding OR invoice_date.",
            "Unrecognized columns are ignored (not rejected).",
            "Common header aliases are auto-mapped, e.g. 'Invoice No' -> invoice_id, 'Supplier' -> vendor_name.",
            "severity and confidence_score are derived by the agent and are NOT required inputs.",
        ],
    }
