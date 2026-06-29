"""End-to-end smoke test in mock mode (no Anthropic / Gemini key required)."""
from __future__ import annotations

from datetime import UTC
from pathlib import Path

import pytest

from app.graph.builder import build_graph, initial_state
from app.schemas import RunStatus

SAMPLE = Path(__file__).parent.parent / "sample_data" / "exception_queue.csv"


@pytest.fixture
def force_mock_mode(monkeypatch):
    """Pin AI provider to mock so the smoke test stays hermetic — never makes
    a real API call even when the developer has provider keys in their shell
    environment.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "")
    monkeypatch.setenv("AZURE_CHAT_OPENAI_ENDPOINT", "")
    # Keep the run store in-memory during tests (no network to Supabase / DB).
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_KEY", "")
    monkeypatch.setenv("DB_PERSISTENCE_ENABLED", "false")
    # Tests exercise the API without tokens — pin auth off regardless of .env.
    monkeypatch.setenv("AUTH_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_pipeline_end_to_end(force_mock_mode):
    graph = build_graph()
    state = initial_state("run_test", "tenant_test")
    state["_input_bytes"] = SAMPLE.read_bytes()  # type: ignore[typeddict-unknown-key]
    state["_input_filename"] = "exception_queue.csv"  # type: ignore[typeddict-unknown-key]

    final = graph.invoke(state)

    assert final["status"] != RunStatus.FAILED
    assert len(final["rows"]) == 25
    assert len(final["classifications"]) == 25
    assert len(final["resolutions"]) == 25
    # Mock client classifies on the ERP-declared type, so we should get
    # at least one non-Other classification.
    types = {c.primary_exception_type.value for c in final["classifications"]}
    assert types & {"Price Variance", "Missing PO", "Duplicate"}
    assert final["metrics"].total_exceptions == 25
    assert final["priority_queues"] is not None
    # Brief #5 mandated distribution
    bt = final["metrics"].breakdown_by_type
    assert bt.get("Price Variance") == 8
    assert bt.get("Missing PO") == 5
    assert bt.get("Duplicate") == 4
    assert bt.get("Quantity Mismatch") == 4
    assert bt.get("Unapproved Vendor") == 4


def test_severity_validator_is_authoritative():
    from decimal import Decimal

    from app.graph.nodes.severity import compute_severity

    assert compute_severity(Decimal("30000"), 5).value == "HIGH"
    assert compute_severity(Decimal("1000"), 45).value == "HIGH"
    assert compute_severity(Decimal("10000"), 10).value == "MEDIUM"
    assert compute_severity(Decimal("100"), 1).value == "LOW"


def test_rules_engine_catchall_enforced():
    from app.config import get_settings
    from app.rules.engine import RulesEngine

    engine = RulesEngine.from_path(get_settings().rules_policy_path)
    assert engine.policy.rules[-1].when == {}


def test_provider_precedence():
    from app.config import Settings

    common_blank = dict(
        anthropic_api_key="",
        gemini_api_key="",
        azure_openai_api_key="",
        azure_chat_openai_endpoint="",
    )

    # No keys → mock
    s = Settings(**common_blank)
    assert s.active_ai_provider == "mock"
    assert s.model_for("classify") == "mock-classify"
    assert s.model_for("draft") == "mock-draft"

    # Anthropic wins when all present
    s = Settings(
        anthropic_api_key="sk-ant",
        gemini_api_key="gk",
        azure_openai_api_key="az",
        azure_chat_openai_endpoint="https://x.openai.azure.com/",
    )
    assert s.active_ai_provider == "anthropic"
    assert s.model_for("classify").startswith("claude-")

    # Gemini fallback when only Gemini key present
    s = Settings(
        **{**common_blank, "gemini_api_key": "gk"},
    )
    assert s.active_ai_provider == "gemini"
    assert s.model_for("classify").startswith("gemini-")
    assert s.model_for("draft").startswith("gemini-")

    # Azure fallback when only Azure key + endpoint present
    s = Settings(
        **{
            **common_blank,
            "azure_openai_api_key": "az",
            "azure_chat_openai_endpoint": "https://retinexopenai.openai.azure.com/",
            "azure_openai_deployment": "gpt-4o-mini",
        },
    )
    assert s.active_ai_provider == "azure"
    assert s.model_for("classify") == "gpt-4o-mini"
    assert s.model_for("draft") == "gpt-4o-mini"

    # Azure key without endpoint → falls through to mock
    s = Settings(**{**common_blank, "azure_openai_api_key": "az"})
    assert s.active_ai_provider == "mock"


def test_post_runs_returns_immediately_with_running_status(force_mock_mode):
    """The HTTP layer must not block on graph execution.

    POST /v1/runs schedules the run as a background task; the response
    should come back with status=RUNNING (or AWAITING_REVIEW only because
    mock mode finishes faster than the response can be sent).
    """
    import time

    from fastapi.testclient import TestClient

    from app.api.main import app

    client = TestClient(app)
    with open(SAMPLE, "rb") as f:
        t0 = time.perf_counter()
        r = client.post(
            "/v1/runs",
            files={"file": ("exception_queue.csv", f, "text/csv")},
            data={"tenant_id": "test"},
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000

    assert r.status_code == 200
    summary = r.json()
    # Must return a run_id and a state-machine status.
    assert summary["run_id"].startswith("run_")
    assert summary["status"] in ("RUNNING", "AWAITING_REVIEW")
    # The response should not include time for AI calls — we just want
    # confirmation it's not waiting for the full pipeline. Allow a generous
    # 3s ceiling so CI variance doesn't flake.
    assert elapsed_ms < 3000, f"POST took {elapsed_ms:.0f}ms; expected non-blocking"


def test_post_runs_rejects_oversized_file(force_mock_mode):
    from fastapi.testclient import TestClient

    from app.api.main import app

    client = TestClient(app)
    huge = b"a,b,c\n" + (b"x" * (26 * 1024 * 1024))  # >25 MB
    r = client.post(
        "/v1/runs",
        files={"file": ("big.csv", huge, "text/csv")},
        data={"tenant_id": "test"},
    )
    assert r.status_code == 413


def test_vendor_profiles_accumulate_across_runs(force_mock_mode, tmp_path, monkeypatch):
    """Running the same CSV twice should double every profile's invoice count."""
    # Point the vendor store at a fresh tmp file so this test is hermetic.
    monkeypatch.setenv("VENDOR_PROFILES_PATH", str(tmp_path / "vendor_profiles.json"))
    from app.config import get_settings
    get_settings.cache_clear()

    # Force a brand-new VendorProfileStore against the tmp path.
    from app.vendor import store as vstore_mod
    vstore_mod.reset_vendor_store()

    from app.graph.builder import build_graph, initial_state

    def _run():
        graph = build_graph()
        state = initial_state("run_vendor_test", "tenant_test")
        state["_input_bytes"] = SAMPLE.read_bytes()  # type: ignore[typeddict-unknown-key]
        state["_input_filename"] = "exception_queue.csv"  # type: ignore[typeddict-unknown-key]
        return graph.invoke(state)

    _run()
    from app.vendor import get_vendor_store
    store = get_vendor_store()
    after_first = {p.vendor_name: p.total_invoices_seen for p in store.get_all()}
    assert len(after_first) == 25, "expected one profile per unique vendor"
    assert all(v == 1 for v in after_first.values())

    _run()
    after_second = {p.vendor_name: p.total_invoices_seen for p in store.get_all()}
    assert len(after_second) == 25
    assert all(v == 2 for v in after_second.values()), (
        "profile counts should double after the second identical run"
    )

    # Reliability score is deterministic — replay yields same value.
    one = store.get("Oracle")
    assert one is not None
    assert 0.0 <= one.reliability_score() <= 1.0


def test_vendor_history_block_prepended_to_prompt():
    """Sanity-check the enrichment helper renders / skips correctly."""
    from datetime import datetime

    from app.schemas import PrimaryExceptionType, ResolutionPath, VendorProfile  # noqa: F401
    from app.vendor.enrichment import render_vendor_context

    # Unseen vendor → empty string
    assert render_vendor_context(None) == ""
    empty_profile = VendorProfile(
        vendor_name="X",
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    assert render_vendor_context(empty_profile) == ""

    seen = VendorProfile(
        vendor_name="Oracle",
        total_invoices_seen=10,
        auto_approved_count=2,
        escalated_count=3,
        exception_type_counts={"Price Variance": 5, "Duplicate": 2},
        first_seen_at=datetime.now(UTC),
        last_seen_at=datetime.now(UTC),
    )
    block = render_vendor_context(seen)
    assert "<vendor_history>" in block and "</vendor_history>" in block
    assert "Oracle" in block
    assert "reliability_score" in block


def test_comms_dispatch_dryrun_writes_eml(force_mock_mode, tmp_path, monkeypatch):
    """Dry-run path should write .eml + .json to artifacts/sent/{run_id}/."""
    monkeypatch.setenv("COMMS_DRYRUN", "true")
    monkeypatch.setenv("COMMS_SENT_DIR", str(tmp_path / "sent"))
    monkeypatch.setenv("GMAIL_SMTP_USER", "ap-agent@example.com")
    monkeypatch.setenv("COMMS_TEST_RECIPIENT", "vendor@example.com")
    monkeypatch.setenv("COMMS_AP_TEAM_MAILBOX", "ap-team@example.com")
    from app.config import get_settings
    get_settings.cache_clear()

    from app.comms import dispatch
    from app.schemas import CommChannel, CommunicationDraft, SendStatus

    d = CommunicationDraft(
        invoice_id="INV-TEST",
        channel=CommChannel.VENDOR_EMAIL,
        recipient_hint="Vendor AR contact",
        subject="Action required: INV-TEST",
        body="Hello, please review invoice INV-TEST.",
        template_id="vendor_price_variance",
        model_id="mock",
    )
    result = dispatch(draft=d, run_id="run_dryrun_test")
    assert result.status == SendStatus.DRYRUN
    assert result.provider == "dryrun"
    assert result.recipient == "vendor@example.com"
    assert result.sent_at is not None

    out_dir = tmp_path / "sent" / "run_dryrun_test"
    json_path = out_dir / "INV-TEST__vendor_email.json"
    eml_path = out_dir / "INV-TEST__vendor_email.eml"
    assert json_path.exists()
    assert eml_path.exists()
    eml_text = eml_path.read_text(encoding="utf-8")
    assert "To: vendor@example.com" in eml_text
    assert "Bcc: ap-team@example.com" in eml_text
    assert "From: ap-agent@example.com" in eml_text


def test_comms_dispatch_idempotent_resend(force_mock_mode, tmp_path, monkeypatch):
    """Sending the same draft twice should return the original result, not re-write."""
    monkeypatch.setenv("COMMS_DRYRUN", "true")
    monkeypatch.setenv("COMMS_SENT_DIR", str(tmp_path / "sent"))
    from app.config import get_settings
    get_settings.cache_clear()

    from app.comms import dispatch
    from app.schemas import CommChannel, CommunicationDraft, SendStatus

    d = CommunicationDraft(
        invoice_id="INV-IDEM",
        channel=CommChannel.INTERNAL_EMAIL,
        recipient_hint="AP Operations",
        body="Test",
        template_id="internal_duplicate",
        model_id="mock",
    )
    first = dispatch(draft=d, run_id="run_idem")
    assert first.status == SendStatus.DRYRUN

    # Mutate the draft to reflect that the first send happened, then retry.
    d_after = d.model_copy(
        update={
            "send_status": SendStatus.DRYRUN,
            "send_provider": "dryrun",
            "send_message_id": first.message_id,
            "recipient": first.recipient,
            "sent_at": first.sent_at,
        }
    )
    second = dispatch(draft=d_after, run_id="run_idem")
    assert second.message_id == first.message_id
    assert second.status == SendStatus.DRYRUN


def test_comms_dispatch_skipped_when_no_recipient(force_mock_mode, monkeypatch):
    """If no recipient can be resolved, dispatch returns SKIPPED, not raises."""
    monkeypatch.setenv("COMMS_DRYRUN", "true")
    monkeypatch.setenv("COMMS_TEST_RECIPIENT", "")  # disable the dev fallback
    monkeypatch.setenv("COMMS_AP_TEAM_MAILBOX", "")
    from app.config import get_settings
    get_settings.cache_clear()

    from app.comms import dispatch
    from app.schemas import CommChannel, CommunicationDraft, SendStatus

    d = CommunicationDraft(
        invoice_id="INV-NORECIP",
        channel=CommChannel.VENDOR_EMAIL,
        recipient_hint="?",
        body="x",
        template_id="vendor_price_variance",
        model_id="mock",
    )
    result = dispatch(draft=d, run_id="run_skip")
    assert result.status == SendStatus.SKIPPED
    assert result.message_id is None


def test_email_template_renders_clean_html(force_mock_mode, monkeypatch):
    """HTML render should escape input, convert '- ' bullets to <ul>/<li>,
    include the signature block, and use the finance-escalation accent."""
    from app.config import get_settings
    get_settings.cache_clear()
    settings = get_settings()

    from app.comms.email_template import render_html, render_text
    from app.schemas import CommChannel, CommunicationDraft

    d = CommunicationDraft(
        invoice_id="INV-2005",
        channel=CommChannel.FINANCE_NOTE,
        recipient_hint="Finance Controller",
        subject="Workday INV-2005 — Price Variance (12%)",
        body=(
            "Dear Finance Controller,\n\n"
            "Workday invoice INV-2005 requires your approval "
            "due to a 12% price variance ($27,500).\n\n"
            "- Vendor: Workday, invoice INV-2005, amount $27,500\n"
            "- Variance: 12% vs PO; exposure approximately $2,946\n"
            "- Root cause: unit rate above contract baseline\n"
            "- Recommended action: approve / reject / request credit note\n\n"
            "Requesting your decision within 8 hours.\n\n"
            "Thank you,"
        ),
        template_id="escalation_controller.v2",
        model_id="mock",
    )
    html = render_html(d, settings)
    assert "<!DOCTYPE html>" in html
    # Channel-aware header
    assert "Finance Escalation" in html
    assert "#b91c1c" in html  # escalation red bar
    # Bullets converted
    assert "<ul" in html and "<li" in html
    assert html.count("<li") == 4
    # Signature block injected (deterministic; not from the LLM)
    assert settings.comms_signature_name in html
    assert settings.comms_signature_company in html
    # Disclaimer present in footer
    assert "confidential" in html.lower()
    # Plain-text variant also has signature appended
    text = render_text(d, settings)
    assert text.rstrip().endswith(
        settings.comms_signature_disclaimer
    ) or settings.comms_signature_name in text


def test_email_template_html_escaping():
    """User-supplied content must be HTML-escaped (no XSS via LLM output)."""
    from app.config import get_settings
    get_settings.cache_clear()
    from app.comms.email_template import render_html
    from app.schemas import CommChannel, CommunicationDraft

    d = CommunicationDraft(
        invoice_id="INV-XSS",
        channel=CommChannel.VENDOR_EMAIL,
        recipient_hint="Vendor",
        subject="Test <script>alert(1)</script>",
        body="Hi <script>alert('x')</script>\n\nNot a real script.",
        template_id="t",
        model_id="m",
    )
    html = render_html(d, get_settings())
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_dryrun_writes_html_preview(force_mock_mode, tmp_path, monkeypatch):
    """Dry-run must write a .html preview alongside the .eml."""
    monkeypatch.setenv("COMMS_DRYRUN", "true")
    monkeypatch.setenv("COMMS_SENT_DIR", str(tmp_path / "sent"))
    monkeypatch.setenv("COMMS_EMAIL_HTML_ENABLED", "true")
    monkeypatch.setenv("GMAIL_SMTP_USER", "agent@example.com")
    monkeypatch.setenv("COMMS_TEST_RECIPIENT", "v@example.com")
    monkeypatch.setenv("COMMS_AP_TEAM_MAILBOX", "ap@example.com")
    from app.config import get_settings
    get_settings.cache_clear()

    from app.comms import dispatch
    from app.schemas import CommChannel, CommunicationDraft

    d = CommunicationDraft(
        invoice_id="INV-PREV",
        channel=CommChannel.VENDOR_EMAIL,
        recipient_hint="Vendor",
        subject="Action required",
        body="Hello vendor,\n\nPlease review INV-PREV.\n\n- Detail line\n\nThank you,",
        template_id="vendor_price_variance",
        model_id="mock",
    )
    dispatch(draft=d, run_id="run_html")

    out_dir = tmp_path / "sent" / "run_html"
    html_path = out_dir / "INV-PREV__vendor_email.html"
    eml_path = out_dir / "INV-PREV__vendor_email.eml"
    assert html_path.exists(), "dryrun should write .html preview"
    assert eml_path.exists()
    html_content = html_path.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html_content
    assert "Vendor Communication" in html_content
    assert "Best regards" in html_content


def test_subject_dedup_in_slack_fallback(force_mock_mode, tmp_path, monkeypatch):
    """When the LLM produces 'Escalation: ...' and the dispatcher prefixes
    '[Finance escalation] ', the result should NOT read '[Finance escalation]
    Escalation: ...'."""
    monkeypatch.setenv("COMMS_DRYRUN", "false")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "")
    monkeypatch.setenv("COMMS_FINANCE_CONTROLLER_MAILBOX", "controller@example.com")
    monkeypatch.setenv("GMAIL_SMTP_USER", "")  # so the SMTP call short-circuits
    from app.config import get_settings
    get_settings.cache_clear()

    # We don't want to actually send; intercept by stubbing out send_email_via_gmail.
    captured: dict = {}

    def fake_send(*, draft, recipient, settings, bcc):
        captured["subject"] = draft.subject
        captured["recipient"] = recipient
        return ("<msg-id>", "ok")

    import app.comms.dispatcher as disp
    monkeypatch.setattr(disp, "send_email_via_gmail", fake_send)

    from app.comms import dispatch
    from app.schemas import CommChannel, CommunicationDraft

    d = CommunicationDraft(
        invoice_id="INV-DEDUP",
        channel=CommChannel.FINANCE_NOTE,
        recipient_hint="Controller",
        subject="Escalation: Workday INV-2005 — Price Variance",
        body="Body",
        template_id="escalation_controller",
        model_id="m",
    )
    dispatch(draft=d, run_id="run_dedup")
    assert "subject" in captured, "dispatcher should have routed via email fallback"
    assert captured["subject"] == "[Finance escalation] Workday INV-2005 — Price Variance"


def test_comms_finance_note_falls_back_to_email_when_slack_missing(
    force_mock_mode, tmp_path
):
    """finance_note + empty SLACK_WEBHOOK_URL → email (dry-run captures it).

    Constructs Settings via init kwargs (highest pydantic-settings precedence)
    so the developer's local `.env` doesn't leak through.
    """
    from app.comms import dispatch
    from app.config import Settings
    from app.schemas import CommChannel, CommunicationDraft, SendStatus

    s = Settings(
        comms_dryrun=True,
        comms_sent_dir=tmp_path / "sent",
        slack_webhook_url="",
        comms_finance_controller_mailbox="controller@example.com",
        comms_ap_team_mailbox="ap@example.com",
        gmail_smtp_user="agent@example.com",
    )
    d = CommunicationDraft(
        invoice_id="INV-ESCAL",
        channel=CommChannel.FINANCE_NOTE,
        recipient_hint="Finance Controller",
        subject="Snowflake $36k variance escalation",
        body="Material price variance flagged for review.",
        template_id="escalation_controller",
        model_id="mock",
    )
    result = dispatch(draft=d, run_id="run_fallback", settings=s)
    assert result.status == SendStatus.DRYRUN
    # Controller mailbox is the highest-precedence resolver target for finance_note.
    assert result.recipient == "controller@example.com"
    # The .eml file should have the [Finance escalation] subject prefix? Not
    # in dry-run since the adaptation happens on the live path. In dry-run we
    # capture the original draft. (That's an acceptable simplification: the
    # dry-run output represents what the dispatch input looked like.)


def test_comms_finance_note_uses_ap_team_when_controller_unset(
    force_mock_mode, tmp_path, monkeypatch
):
    """No controller mailbox → falls back to AP team mailbox."""
    monkeypatch.setenv("COMMS_DRYRUN", "true")
    monkeypatch.setenv("COMMS_SENT_DIR", str(tmp_path / "sent"))
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "")
    monkeypatch.setenv("COMMS_FINANCE_CONTROLLER_MAILBOX", "")
    monkeypatch.setenv("COMMS_AP_TEAM_MAILBOX", "ap@example.com")
    from app.config import get_settings
    get_settings.cache_clear()

    from app.comms import dispatch
    from app.schemas import CommChannel, CommunicationDraft, SendStatus

    d = CommunicationDraft(
        invoice_id="INV-FALLBACK2",
        channel=CommChannel.FINANCE_NOTE,
        recipient_hint="?",
        body="Escalation note",
        template_id="escalation_controller",
        model_id="mock",
    )
    result = dispatch(draft=d, run_id="run_fb2")
    assert result.status == SendStatus.DRYRUN
    assert result.recipient == "ap@example.com"


def test_comms_send_endpoint_dryrun(force_mock_mode, tmp_path, monkeypatch):
    """End-to-end through the API: run pipeline, then send one draft."""
    monkeypatch.setenv("COMMS_DRYRUN", "true")
    monkeypatch.setenv("COMMS_SENT_DIR", str(tmp_path / "sent"))
    # Force every channel's recipient to the same address so the assertion
    # below holds regardless of which draft happens to be first in the run.
    monkeypatch.setenv("COMMS_TEST_RECIPIENT", "test@example.com")
    monkeypatch.setenv("COMMS_AP_TEAM_MAILBOX", "test@example.com")
    monkeypatch.setenv("COMMS_FINANCE_CONTROLLER_MAILBOX", "test@example.com")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "")
    monkeypatch.setenv("VENDOR_PROFILES_PATH", str(tmp_path / "v.json"))
    from app.config import get_settings
    get_settings.cache_clear()
    from app.vendor import store as vstore_mod
    vstore_mod.reset_vendor_store()

    from fastapi.testclient import TestClient

    from app.api.main import app
    c = TestClient(app)

    with open(SAMPLE, "rb") as f:
        r = c.post(
            "/v1/runs",
            files={"file": ("exception_queue.csv", f, "text/csv")},
            data={"tenant_id": "t"},
        )
    rid = r.json()["run_id"]

    # Wait for run to complete (mock mode finishes within a few hundred ms).
    import time
    for _ in range(40):
        if c.get(f"/v1/runs/{rid}").json().get("status") in (
            "AWAITING_REVIEW",
            "COMPLETED",
            "FAILED",
        ):
            break
        time.sleep(0.1)

    sent_payload = c.get(f"/v1/runs/{rid}/sent").json()
    drafts = sent_payload["drafts"]
    assert len(drafts) > 0
    # Every draft should still be in 'draft' status before sending.
    assert all(d["send_status"] == "draft" for d in drafts)

    # Send the first draft.
    target = drafts[0]["invoice_id"]
    result = c.post(f"/v1/runs/{rid}/drafts/{target}/send", json={}).json()
    assert result["status"] == "dryrun"
    assert result["recipient"] == "test@example.com"

    # Listing should now show 1 dryrun + the rest still draft.
    after = c.get(f"/v1/runs/{rid}/sent").json()["drafts"]
    sent_or_dryrun = [d for d in after if d["send_status"] in ("dryrun", "sent")]
    assert len(sent_or_dryrun) == 1
    assert sent_or_dryrun[0]["invoice_id"] == target


def test_ai_client_picks_mock_when_no_keys():
    from app.ai.client import ClaudeClient
    from app.config import Settings

    client = ClaudeClient(
        Settings(
            anthropic_api_key="",
            gemini_api_key="",
            azure_openai_api_key="",
            azure_chat_openai_endpoint="",
        )
    )
    assert client.provider == "mock"
    assert client.is_mock
