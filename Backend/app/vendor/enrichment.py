"""Vendor context block — used to enrich the classifier prompt with history.

Rendered as JSON inside a <vendor_history> tag so the classifier treats it
as data (not instructions) — the same prompt-injection guard pattern used
for the exception payload itself.
"""
from __future__ import annotations

import json

from app.schemas import VendorProfile


def top_n(d: dict[str, int], n: int = 3) -> list[tuple[str, int]]:
    return sorted(d.items(), key=lambda kv: -kv[1])[:n]


def render_vendor_context(profile: VendorProfile | None) -> str:
    """Return a `<vendor_history>...</vendor_history>` block, or empty string.

    Returns empty string for unseen vendors so the classifier behaves
    identically to its v0 prompt — no history, no bias.
    """
    if profile is None or profile.total_invoices_seen == 0:
        return ""

    n = profile.total_invoices_seen
    payload = {
        "vendor": profile.vendor_name,
        "invoices_seen": n,
        "reliability_score": profile.reliability_score(),
        "top_exception_types": [k for k, _ in top_n(profile.exception_type_counts, 3)],
        "top_resolution_paths": [k for k, _ in top_n(profile.resolution_path_counts, 3)],
        "auto_approve_rate": round(profile.auto_approved_count / n, 3),
        "escalation_rate": round(profile.escalated_count / n, 3),
        "duplicate_rate": round(profile.duplicate_count / n, 3),
        "missing_po_rate": round(profile.missing_po_count / n, 3),
        "avg_variance_pct": (
            round(profile.average_variance_pct, 2)
            if profile.average_variance_pct is not None
            else None
        ),
        "avg_days_outstanding": round(profile.average_days_outstanding, 1),
    }
    return (
        "<vendor_history>\n"
        + json.dumps(payload)
        + "\n</vendor_history>"
    )
