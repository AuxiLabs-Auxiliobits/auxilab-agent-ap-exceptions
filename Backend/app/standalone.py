"""Standalone, in-process entry point for the AP Exception Handling agent.

This is the packaging seam that lets the LangGraph pipeline run as a plain
Python tool — no FastAPI server, no web frontend, no auth. Both the CLI
(`cli.py`) and the Gradio UI (`ui.py`) call into here.

    csv bytes ──► run_pipeline() ──► final RunState ──► build_report() ──► dict
                                                     └► render_summary() ──► text

The heavy lifting (ingest → classify → severity → route → draft → prioritize →
persist) is unchanged: we reuse `execute_run` with an in-memory store, exactly
as the test suite and the API do. Runs fully offline in deterministic mock mode
when no AI provider key is configured.
"""
from __future__ import annotations

from pathlib import Path

from app.ai.client import ClaudeClient
from app.api.runner import execute_run
from app.api.store import RunStore
from app.graph.nodes.persist import _to_jsonable
from app.graph.state import RunState
from app.schemas.resolution import RESOLUTION_PATH_LABELS

# Fixed identity for standalone runs — there is no multi-tenant auth here.
_LOCAL_TENANT = "local"


def ai_mode() -> str:
    """Which AI backend the pipeline will use: 'mock', 'anthropic', etc.

    'mock' means no provider key is set and the run is fully deterministic
    and offline — the demo default.
    """
    return ClaudeClient().provider


# --------------------------------------------------------------------------- #
# Run                                                                          #
# --------------------------------------------------------------------------- #
def run_pipeline(content: bytes, filename: str = "input.csv") -> RunState:
    """Run the full agent pipeline over one CSV payload and return final state."""
    store = RunStore()
    return execute_run(
        content=content,
        filename=filename,
        tenant_id=_LOCAL_TENANT,
        store=store,
    )


def run_pipeline_path(csv_path: str | Path) -> RunState:
    """Run the pipeline over a CSV file on disk."""
    path = Path(csv_path)
    content = path.read_bytes()
    return run_pipeline(content, filename=path.name)


# --------------------------------------------------------------------------- #
# Report shaping                                                              #
# --------------------------------------------------------------------------- #
def build_report(state: RunState) -> dict:
    """Turn the raw pipeline state into a clean, JSON-serializable report.

    Joins per-invoice classification / resolution / priority into one list of
    rows, plus a top-level summary and the quarantined (rejected) rows.
    """
    snap = _to_jsonable(state)

    classifications = {c["invoice_id"]: c for c in snap.get("classifications", [])}
    resolutions = {r["invoice_id"]: r for r in snap.get("resolutions", [])}
    drafts = {d["invoice_id"]: d for d in snap.get("drafts", [])}

    priority_by_invoice: dict[str, dict] = {}
    pq = snap.get("priority_queues") or {}
    for bucket in ("high", "medium", "low"):
        for entry in pq.get(bucket, []):
            entry = dict(entry)
            entry["bucket"] = bucket
            priority_by_invoice[entry["invoice_id"]] = entry

    exceptions = []
    for row in snap.get("rows", []):
        inv = row["invoice_id"]
        cls = classifications.get(inv, {})
        res = resolutions.get(inv, {})
        pr = priority_by_invoice.get(inv, {})
        exceptions.append(
            {
                "invoice_id": inv,
                "vendor_name": row.get("vendor_name"),
                "invoice_amount": row.get("invoice_amount"),
                "exception_type": row.get("exception_type"),
                "classification": {
                    "primary_type": cls.get("primary_exception_type"),
                    "severity": cls.get("severity"),
                    "root_cause": cls.get("root_cause"),
                    "confidence": cls.get("confidence_score"),
                },
                "resolution": {
                    "path": res.get("resolution_path"),
                    "recommended_approach": RESOLUTION_PATH_LABELS.get(
                        res.get("resolution_path"), res.get("resolution_path")
                    ),
                    "requires_communication": res.get("requires_communication"),
                    "sla_hours": res.get("sla_hours"),
                    "rule_id": res.get("rule_id"),
                },
                "priority": {
                    "bucket": pr.get("bucket"),
                    "score": pr.get("priority_score"),
                },
                "has_draft": inv in drafts,
            }
        )

    return {
        "run_id": snap.get("run_id"),
        "status": str(snap.get("status")),
        "ai_mode": ai_mode(),
        "summary": snap.get("metrics"),
        "exceptions": exceptions,
        "drafts": list(drafts.values()),
        "quarantined": snap.get("quarantined", []),
    }


def render_summary(report: dict) -> str:
    """Human-readable one-screen summary of a report."""
    m = report.get("summary") or {}
    lines = [
        "AP Exception Handling - Run Summary",
        "=" * 40,
        f"Run ID          : {report.get('run_id')}",
        f"Status          : {report.get('status')}",
        f"AI mode         : {report.get('ai_mode')}"
        + ("  (offline demo - no API key)" if report.get("ai_mode") == "mock" else ""),
        "",
        f"Total exceptions   : {m.get('total_exceptions', 0)}",
        f"Auto-resolvable    : {m.get('auto_resolvable_count', 0)}",
        f"Need escalation    : {m.get('escalations_required', 0)}",
        f"SLA at risk        : {m.get('sla_at_risk_count', 0)}",
        f"Total value        : {m.get('total_exception_value', 0)}",
        f"Avg AI confidence  : {m.get('average_confidence', 0)}",
        f"Rejected rows      : {len(report.get('quarantined', []))}",
    ]

    by_type = m.get("breakdown_by_type") or {}
    if by_type:
        lines.append("")
        lines.append("By exception type:")
        for k, v in by_type.items():
            lines.append(f"  - {k}: {v}")

    top = m.get("top_5_actionable") or []
    if top:
        lines.append("")
        lines.append("Top actionable:")
        for e in top:
            lines.append(
                f"  - {e.get('invoice_id')}  "
                f"(score {e.get('priority_score')}, {e.get('bucket')})"
            )
    return "\n".join(lines)
