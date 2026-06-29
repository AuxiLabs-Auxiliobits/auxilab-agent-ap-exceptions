"""'Ask the desk' — a read-only, grounded assistant over a run's real data.

Numbers are computed from the run state (metrics, SLA, cases, classifications,
resolutions), so the assistant can never invent a figure and every number is
auditable — exactly what a finance team needs. It explains and summarises; it
never decides or acts.

This module is the **deterministic core**: it computes every answer from run
state. It is provider-free and synchronous, so it always works (and is what the
assistant falls back to when no LLM is configured). The hybrid layer in
``assistant_hybrid.py`` adds LLM *understanding* (robust intent + entity
extraction instead of keyword matching) and RAG (semantic search over invoice
notes for free-form questions) on top — but routes back here for every numeric
answer, so figures stay deterministic.

The branch bodies are factored into ``_answer_*`` functions keyed by intent so
both paths share one implementation: the keyword cascade in ``answer_question``
and the LLM router in ``answer_for_intent`` select the same functions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.schemas import resolution_path_label

_CLOSED = {"RESOLVED", "WONT_FIX"}

# Intents the deterministic core can answer directly. "search" (free-text RAG)
# and the empty-run case are handled by the hybrid layer / answer_question.
DETERMINISTIC_INTENTS = frozenset(
    {
        "invoice",
        "follow_up",
        "sla",
        "escalations",
        "severity",
        "vendors",
        "duplicates",
        "summary",
        "out_of_scope",
    }
)


def _money(v) -> str:
    try:
        return f"${float(v):,.0f}"
    except (TypeError, ValueError):
        return "n/a"


def _case_status(cases: dict, inv: str) -> str:
    c = cases.get(inv)
    return (c or {}).get("status", "OPEN")


def _match_invoice(question: str, invoice_ids) -> str | None:
    """Resolve a specific invoice the question refers to — by full id
    ("INV-2009") OR a distinguishing number ("2009" / "invoice 2009"). Returns
    None if nothing matches or the reference is ambiguous (matches >1 invoice)."""
    ids = list(invoice_ids)
    q_up = question.upper()

    # 1) The full id as a whole token.
    for inv in ids:
        if re.search(rf"\b{re.escape(inv.upper())}\b", q_up):
            return inv

    # 2) A numeric token that uniquely identifies one invoice (e.g. "2009").
    by_token: dict[str, set[str]] = {}
    for inv in ids:
        tokens = set(re.findall(r"\d+", inv))
        if "-" in inv:
            tokens.add(inv.rsplit("-", 1)[-1].upper())
        for t in tokens:
            by_token.setdefault(t, set()).add(inv)
    for tok in re.findall(r"[A-Z0-9]+", q_up):
        cand = by_token.get(tok)
        if cand and len(cand) == 1:
            return next(iter(cand))
    return None


# --------------------------------------------------------------------------- #
# Shared computation context                                                   #
# --------------------------------------------------------------------------- #
@dataclass
class _Ctx:
    rows: dict
    cls: dict
    res: dict
    cases: dict
    metrics: Any
    sla: dict


def _build_ctx(state: dict, *, now: datetime) -> _Ctx:
    from app.comms.sla import evaluate_sla

    return _Ctx(
        rows={r.invoice_id: r for r in state.get("rows", [])},
        cls={c.invoice_id: c for c in state.get("classifications", [])},
        res={r.invoice_id: r for r in state.get("resolutions", [])},
        cases=state.get("cases", {}) or {},
        metrics=state.get("metrics"),
        # Actionable view: a resolved/won't-fix case is off the clock, so the
        # assistant's "what's at risk" matches the UI's SLA tracker.
        sla=evaluate_sla(state, now=now, due_soon_hours=4.0, exclude_closed=True),
    )


def _line(ctx: _Ctx, inv: str) -> str:
    row = ctx.rows.get(inv)
    r = ctx.res.get(inv)
    vendor = getattr(row, "vendor_name", "unknown")
    amt = _money(getattr(row, "invoice_amount", None))
    path = resolution_path_label(r.resolution_path) if r is not None else "—"
    return f"{inv} · {vendor} · {amt} · {path} · case {_case_status(ctx.cases, inv)}"


# --------------------------------------------------------------------------- #
# Per-intent deterministic answers (each returns the response dict)           #
# --------------------------------------------------------------------------- #
def _answer_invoice(ctx: _Ctx, inv: str) -> dict:
    row = ctx.rows[inv]
    c = ctx.cls.get(inv)
    r = ctx.res.get(inv)
    parts = [f"{inv} — {getattr(row, 'vendor_name', 'unknown')}, {_money(getattr(row, 'invoice_amount', None))}."]
    if c is not None:
        parts.append(
            f"Classified as {c.primary_exception_type.value}, {c.severity.value} severity "
            f"(confidence {round(c.confidence_score * 100)}%)."
        )
        if getattr(c, "root_cause", None):
            parts.append(f"Root cause: {c.root_cause}.")
    if r is not None:
        parts.append(f"Routed to {resolution_path_label(r.resolution_path)} (SLA {r.sla_hours}h) by rule {r.rule_id}.")
    parts.append(f"Resolution case status: {_case_status(ctx.cases, inv)}.")
    return {"answer": " ".join(parts), "cited_invoice_ids": [inv], "intent": "invoice"}


def _answer_follow_up(ctx: _Ctx) -> dict:
    closed = {i for i, c in ctx.cases.items() if c.get("status") in _CLOSED}
    fu = [i for i in ctx.sla["breached_items"] if i["invoice_id"] not in closed]
    if not fu:
        return {"answer": "Nothing needs follow-up right now — no breached item is still open.", "cited_invoice_ids": [], "intent": "follow_up"}
    ids = [i["invoice_id"] for i in fu[:10]]
    body = "\n".join(f"  • {_line(ctx, i)}" for i in ids)
    return {
        "answer": f"{len(fu)} item(s) need follow-up (past SLA and still open):\n{body}\n→ open the Resolution Tracker to act on them.",
        "cited_invoice_ids": ids,
        "intent": "follow_up",
    }


def _answer_sla(ctx: _Ctx) -> dict:
    ids = [i["invoice_id"] for i in ctx.sla["breached_items"][:10]]
    body = "\n".join(f"  • {_line(ctx, i)}" for i in ids) if ids else "  (none)"
    return {
        "answer": f"{ctx.sla['breached']} past SLA, {ctx.sla['due_soon']} due soon.\nBreached (most overdue first):\n{body}",
        "cited_invoice_ids": ids,
        "intent": "sla",
    }


def _answer_escalations(ctx: _Ctx) -> dict:
    esc = [i for i, r in ctx.res.items() if r.resolution_path.value == "ESCALATE_CONTROLLER"]
    body = "\n".join(f"  • {_line(ctx, i)}" for i in esc[:10]) if esc else "  (none)"
    return {"answer": f"{len(esc)} invoice(s) escalated to a controller:\n{body}", "cited_invoice_ids": esc[:10], "intent": "escalations"}


def _answer_severity(ctx: _Ctx) -> dict:
    high = [i for i, c in ctx.cls.items() if c.severity.value == "HIGH"]
    body = "\n".join(f"  • {_line(ctx, i)}" for i in high[:10]) if high else "  (none)"
    return {"answer": f"{len(high)} HIGH-severity exception(s):\n{body}", "cited_invoice_ids": high[:10], "intent": "severity"}


def _answer_vendors(ctx: _Ctx) -> dict:
    counts: dict[str, int] = {}
    invoices_by_vendor: dict[str, list[str]] = {}
    for inv, row in ctx.rows.items():
        v = row.vendor_name
        counts[v] = counts.get(v, 0) + 1
        invoices_by_vendor.setdefault(v, []).append(inv)

    total_vendors = len(counts)
    total_exceptions = sum(counts.values())
    # Rank by count desc, then name — repeat offenders (>1) are the vendors worth
    # chasing as a batch.
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    repeat = [(v, n) for v, n in ranked if n > 1]

    lines = [f"{total_vendors} vendor(s) across {total_exceptions} exception(s) in this run."]
    if repeat:
        lines.append(f"{len(repeat)} vendor(s) with more than one exception (most first):")
        lines += [f"  • {v} — {n} exception(s)" for v, n in repeat]
        cited = [inv for v, _ in repeat for inv in invoices_by_vendor[v]][:10]
    else:
        lines.append("No vendor has more than one exception — each vendor below appears once:")
        lines += [f"  • {v} — {n} exception(s)" for v, n in ranked[:5]]
        if total_vendors > 5:
            lines.append(f"  …and {total_vendors - 5} more.")
        cited = []
    return {"answer": "\n".join(lines), "cited_invoice_ids": cited, "intent": "vendors"}


def _answer_duplicates(ctx: _Ctx) -> dict:
    dups = [i for i, c in ctx.cls.items() if c.primary_exception_type.value == "Duplicate"]
    msg = f"{len(dups)} invoice(s) flagged as a Duplicate type in this run." if dups else "No duplicate-type exceptions in this run."
    return {"answer": f"{msg} For cross-run double-pay checks, open the Duplicate Check page.", "cited_invoice_ids": dups[:10], "intent": "duplicates"}


def _answer_summary(ctx: _Ctx) -> dict:
    m = ctx.metrics
    total = m.total_exceptions if m is not None else len(ctx.rows)
    auto = m.auto_resolvable_count if m is not None else 0
    esc_n = m.escalations_required if m is not None else 0
    value = _money(m.total_exception_value) if m is not None else "n/a"
    closed = sum(1 for c in ctx.cases.values() if c.get("status") in _CLOSED)
    summary = (
        f"Run summary: {total} exception(s) worth {value}. "
        f"{auto} auto-resolvable, {esc_n} escalated, {ctx.sla['breached']} past SLA, {closed} resolved."
    )
    return {"answer": summary, "cited_invoice_ids": [], "intent": "summary"}


def _answer_out_of_scope() -> dict:
    return {
        "answer": (
            "I can only answer questions about this run's accounts-payable exceptions — "
            "I don't have anything else. Try: follow-ups, SLA risk, escalations, high "
            'severity, vendors, duplicates, a summary, or a specific invoice (e.g. "why '
            'did INV-2001 escalate?").'
        ),
        "cited_invoice_ids": [],
        "intent": "out_of_scope",
    }


def _empty_run() -> dict:
    return {
        "answer": "This run has no processed exceptions yet — upload a queue and let it finish, then ask again.",
        "cited_invoice_ids": [],
        "intent": "empty",
    }


# --------------------------------------------------------------------------- #
# Entry points                                                                #
# --------------------------------------------------------------------------- #
def answer_for_intent(
    state: dict,
    *,
    intent: str,
    now: datetime,
    invoice_ids: list[str] | None = None,
) -> dict:
    """Deterministic answer for an LLM-classified intent + entities.

    Numbers come from run state; the LLM only chose the intent and pulled out
    entities. Returns None-safe response dicts identical in shape to
    ``answer_question``. ``invoice_ids`` is used only for the ``invoice`` intent
    (first id that exists in the run; ambiguous/missing falls back to summary)."""
    if not state.get("rows"):
        return _empty_run()
    ctx = _build_ctx(state, now=now)

    if intent == "invoice":
        inv = None
        for cand in invoice_ids or []:
            # Tolerate bare numbers / partial ids by matching against the run.
            inv = _match_invoice(str(cand), ctx.rows.keys())
            if inv is not None:
                break
        if inv is None:
            return _answer_summary(ctx)
        return _answer_invoice(ctx, inv)
    if intent == "follow_up":
        return _answer_follow_up(ctx)
    if intent == "sla":
        return _answer_sla(ctx)
    if intent == "escalations":
        return _answer_escalations(ctx)
    if intent == "severity":
        return _answer_severity(ctx)
    if intent == "vendors":
        return _answer_vendors(ctx)
    if intent == "duplicates":
        return _answer_duplicates(ctx)
    if intent == "summary":
        return _answer_summary(ctx)
    return _answer_out_of_scope()


def answer_question(state: dict, question: str, *, now: datetime) -> dict:
    """Deterministic, keyword-routed Q&A — the always-available fallback.

    Returns ``{answer, cited_invoice_ids, intent}`` grounded in run state. This
    is the path used when no LLM is configured; the hybrid layer prefers LLM
    routing but reuses the same ``_answer_*`` functions."""
    q = (question or "").strip()
    ql = q.lower()

    if not state.get("rows"):
        return _empty_run()
    ctx = _build_ctx(state, now=now)

    # 1. A specific invoice ("amount of invoice 2009?", "why did INV-1 escalate?")
    inv = _match_invoice(q, ctx.rows.keys())
    if inv is not None:
        return _answer_invoice(ctx, inv)

    # 2. Needs follow-up
    if any(k in ql for k in ("follow", "overdue", "chase", "stuck", "stall", "behind")):
        return _answer_follow_up(ctx)

    # 3. SLA / at risk
    if any(k in ql for k in ("sla", "risk", "breach", "due", "deadline", "late")):
        return _answer_sla(ctx)

    # 4. Escalations
    if "escalat" in ql:
        return _answer_escalations(ctx)

    # 5. High severity
    if any(k in ql for k in ("severe", "severity", "high", "urgent", "serious")):
        return _answer_severity(ctx)

    # 6. Vendors
    if any(k in ql for k in ("vendor", "supplier", "who")):
        return _answer_vendors(ctx)

    # 7. Duplicates
    if "duplicate" in ql or "double" in ql:
        return _answer_duplicates(ctx)

    # 8. Summary (only when explicitly asked)
    if any(
        k in ql
        for k in (
            "summary", "summarise", "summarize", "overview", "status", "breakdown",
            "stats", "how many", "how much", "total", "count", "going on", "stand",
            "what's in", "whats in", "tell me about this run", "the run",
        )
    ):
        return _answer_summary(ctx)

    # 9. Out of scope — don't guess, and never dump the summary
    return _answer_out_of_scope()
