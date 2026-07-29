"""Offline (mock-mode) tests for the standalone agent — the CLI/UI entry point.

These cover the path a new user actually takes from the README quickstart:
feed `examples/sample_exceptions.csv` to the agent with no API key and no
server, and get back a triaged report.

Deliberately dependency-light: nothing here imports FastAPI, SQLAlchemy or
Gradio, so the suite runs against a lean `pip install -e .` (see the `server`
extra in pyproject.toml). `test_smoke.py` covers the graph itself against the
25-row `sample_data/exception_queue.csv`; this file covers the packaging seam
in `app/standalone.py` and the report it hands to the CLI and the UI.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.schemas import RunStatus

SAMPLE = Path(__file__).parent.parent / "examples" / "sample_exceptions.csv"

# The sample queue is fixed input, so mock mode is fully deterministic and
# these can be asserted exactly rather than by shape alone.
EXPECTED_ROWS = 10
EXPECTED_HIGH = ["INV-2001", "INV-2004", "INV-2008", "INV-2006", "INV-2002"]


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    """One pipeline run over the sample CSV, shared by every test in this module.

    Module-scoped because a full run takes a few seconds and none of these
    tests mutate the result. `pytest.MonkeyPatch()` is used directly since the
    built-in `monkeypatch` fixture is function-scoped.
    """
    mp = pytest.MonkeyPatch()
    # Pin the run hermetic: mock AI provider, no durable store, no real network,
    # regardless of what the developer has in their shell or .env.
    for key in (
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "AZURE_CHAT_OPENAI_ENDPOINT",
        "SUPABASE_URL",
        "SUPABASE_KEY",
    ):
        mp.setenv(key, "")
    mp.setenv("DB_PERSISTENCE_ENABLED", "false")
    # Snapshots land in a temp dir instead of the working tree's ./artifacts.
    mp.setenv("ARTIFACT_DIR", str(tmp_path_factory.mktemp("artifacts")))

    from app.config import get_settings

    get_settings.cache_clear()

    from app.standalone import ai_mode, build_report, run_pipeline_path

    state = run_pipeline_path(SAMPLE)
    yield {"state": state, "report": build_report(state), "ai_mode": ai_mode()}

    mp.undo()
    get_settings.cache_clear()


def test_sample_csv_runs_offline_in_mock_mode(run):
    """With no provider key the whole pipeline completes offline."""
    assert run["ai_mode"] == "mock"

    report = run["report"]
    assert report["ai_mode"] == "mock"
    assert report["status"] == str(RunStatus.AWAITING_REVIEW)
    assert len(report["exceptions"]) == EXPECTED_ROWS
    assert report["quarantined"] == []
    assert report["summary"]["total_exceptions"] == EXPECTED_ROWS

    # Every row is classified, routed and scored — no half-populated entries.
    for exc in report["exceptions"]:
        assert exc["classification"]["primary_type"]
        assert exc["classification"]["severity"] in {"HIGH", "MEDIUM", "LOW"}
        assert exc["resolution"]["path"]
        assert exc["priority"]["bucket"] in {"high", "medium", "low"}


def test_report_contains_high_priority_items(run):
    """The output surfaces HIGH-priority work — the point of the triage."""
    report = run["report"]
    high = [e for e in report["exceptions"] if e["priority"]["bucket"] == "high"]

    assert high, "expected at least one HIGH priority exception"
    assert {e["invoice_id"] for e in high} == set(EXPECTED_HIGH)

    # Nothing high-priority may be waved through, and each one carries an SLA.
    for exc in high:
        assert exc["resolution"]["path"] != "AUTO_APPROVE"
        assert exc["resolution"]["sla_hours"] > 0

    by_id = {e["invoice_id"]: e for e in high}
    # INV-2001 — $182k, 61 days, 14% over PO — goes to the controller.
    assert by_id["INV-2001"]["resolution"]["path"] == "ESCALATE_CONTROLLER"
    # INV-2004 — a quantity mismatch — chases the goods receipt note instead.
    assert by_id["INV-2004"]["resolution"]["path"] == "REQUEST_GRN"

    # `top_5_actionable` is the queue the operator works first.
    top5 = report["summary"]["top_5_actionable"]
    assert [e["invoice_id"] for e in top5] == EXPECTED_HIGH


def test_drafted_communications_are_non_empty(run):
    """Every exception needing an email gets a usable draft."""
    report = run["report"]
    drafts = report["drafts"]
    needs_comms = [
        e for e in report["exceptions"] if e["resolution"]["requires_communication"]
    ]

    assert needs_comms, "sample should produce at least one communication"
    assert len(drafts) == len(needs_comms)
    assert {d["invoice_id"] for d in drafts} == {e["invoice_id"] for e in needs_comms}
    assert all(e["has_draft"] for e in needs_comms)

    for draft in drafts:
        assert draft["subject"].strip(), f"empty subject on {draft['invoice_id']}"
        assert draft["body"].strip(), f"empty body on {draft['invoice_id']}"
        assert draft["channel"]
        # An unrendered template placeholder would ship "{vendor_name}" to a
        # vendor — cheap to assert, embarrassing to miss.
        assert "{" not in draft["body"], f"unrendered placeholder in {draft['invoice_id']}"
        # Drafts are proposals: nothing is sent without human review.
        assert draft["send_status"] == "draft"


def test_priority_queue_is_sorted(run):
    """Each bucket is ordered by the documented key: score desc, then age,
    then amount, then invoice_id ascending."""
    state = run["state"]
    queues = state["priority_queues"]
    rows = {r.invoice_id: r for r in state["rows"]}

    def sort_key(entry):
        row = rows[entry.invoice_id]
        return (
            -entry.priority_score,
            -row.days_outstanding,
            -float(row.invoice_amount),
            entry.invoice_id,
        )

    for bucket in (queues.high, queues.medium, queues.low):
        scores = [e.priority_score for e in bucket]
        assert scores == sorted(scores, reverse=True)
        assert [e.invoice_id for e in bucket] == [
            e.invoice_id for e in sorted(bucket, key=sort_key)
        ]

    # INV-2003 and INV-2009 are duplicates of each other: identical score, age
    # and amount, so only the invoice_id tiebreak separates them.
    low_ids = [e.invoice_id for e in queues.low]
    assert low_ids.index("INV-2003") < low_ids.index("INV-2009")

    assert [e.invoice_id for e in state["metrics"].top_5_actionable] == EXPECTED_HIGH


def test_cli_writes_json_report(run, tmp_path, capsys):
    """`python cli.py <csv> --out report.json` works end to end."""
    import cli

    out = tmp_path / "report.json"
    assert cli.main([str(SAMPLE), "--out", str(out)]) == 0

    printed = capsys.readouterr().out
    assert "AP Exception Handling - Run Summary" in printed
    assert "mock" in printed

    report = json.loads(out.read_text(encoding="utf-8"))
    assert len(report["exceptions"]) == EXPECTED_ROWS
    assert report["ai_mode"] == "mock"


def test_cli_rejects_a_missing_file(tmp_path, capsys):
    """A bad path exits non-zero with a message instead of a traceback."""
    import cli

    assert cli.main([str(tmp_path / "nope.csv")]) == 2
    assert "no such file" in capsys.readouterr().err
