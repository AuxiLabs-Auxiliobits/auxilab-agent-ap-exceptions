"""Tests for the production-hardening changes.

Covers config safety gates, real readiness probe, metrics + AI cost accounting,
the vendor-master recipient lookup, the per-domain comms daily cap, the
in-memory store mutation path, the rules engine routing, and direct
classify/draft AI-node coverage (mock mode — hermetic, no API keys)."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.graph.builder import initial_state
from app.schemas import (
    ClassificationResult,
    CommChannel,
    CommunicationDraft,
    ExceptionRow,
    PrimaryExceptionType,
    ResolutionDecision,
    ResolutionPath,
    SendStatus,
    Severity,
)


@pytest.fixture
def mock_mode(monkeypatch, tmp_path):
    """Pin AI + stores to hermetic, offline mode and clear cached singletons."""
    for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "AZURE_OPENAI_API_KEY",
              "AZURE_CHAT_OPENAI_ENDPOINT", "SUPABASE_URL", "SUPABASE_KEY"):
        monkeypatch.setenv(k, "")
    monkeypatch.setenv("DB_PERSISTENCE_ENABLED", "false")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("VENDOR_PROFILES_PATH", str(tmp_path / "vendor_profiles.json"))
    from app.config import get_settings
    get_settings.cache_clear()
    from app.vendor import store as vstore_mod
    vstore_mod.reset_vendor_store()
    yield
    get_settings.cache_clear()


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #


def _row(invoice_id="INV-1", vendor="Workday", amount="27500", desc="Invoice exceeds PO by 12%",
         etype="Price Variance", days=10) -> ExceptionRow:
    return ExceptionRow(
        invoice_id=invoice_id,
        vendor_name=vendor,
        invoice_amount=Decimal(amount),
        po_number="PO-1",
        exception_type=etype,
        exception_description=desc,
        days_outstanding=days,
    )


def _classification(invoice_id="INV-1", etype=PrimaryExceptionType.PRICE_VARIANCE,
                    conf=0.82, sev=Severity.HIGH) -> ClassificationResult:
    return ClassificationResult(
        invoice_id=invoice_id,
        primary_exception_type=etype,
        root_cause="rc",
        severity_ai_suggested=sev,
        severity=sev,
        confidence_score=conf,
        rationale="r",
        model_id="mock",
        prompt_version="v1",
    )


# --------------------------------------------------------------------------- #
# Config safety gates
# --------------------------------------------------------------------------- #


def test_is_protected_env_matches_prefixes():
    from app.config import Settings

    assert Settings(environment="production").is_protected_env
    assert Settings(environment="PROD").is_protected_env
    assert Settings(environment="prod-us-west").is_protected_env
    assert Settings(environment="staging").is_protected_env
    assert not Settings(environment="dev").is_protected_env
    assert not Settings(environment="test").is_protected_env


def test_resolved_log_level_valid_and_invalid():
    import logging

    from app.config import Settings

    assert Settings(log_level="debug").resolved_log_level == logging.DEBUG
    assert Settings(log_level="WARNING").resolved_log_level == logging.WARNING
    with pytest.raises(ValueError):
        _ = Settings(log_level="DEBGU").resolved_log_level


def test_create_app_refuses_insecure_production(monkeypatch):
    # Import first (under the default dev env) so the module-level
    # `app = create_app()` doesn't trip the gate during import.
    from app.api.main import create_app
    from app.config import get_settings

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="Insecure production config"):
        create_app()
    get_settings.cache_clear()


def test_protected_env_requires_durable_queue(monkeypatch):
    """A prod deploy must enable the durable run queue: fire-and-forget runs are
    lost on restart, so the boot gate refuses without RUN_QUEUE_ENABLED."""
    from app.api.main import create_app
    from app.config import get_settings

    # Everything else satisfied → the ONLY remaining problem is the queue.
    for k, v in {
        "ENVIRONMENT": "production",
        "AUTH_ENABLED": "true",
        "CORS_ALLOW_ORIGINS": "https://app.example.com",
        "RUN_STORE_BACKEND": "db",
        "COMMS_DRYRUN": "true",
        "RUN_QUEUE_ENABLED": "false",
    }.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="RUN_QUEUE_ENABLED"):
        create_app()

    # Enabling the durable queue clears the gate.
    monkeypatch.setenv("RUN_QUEUE_ENABLED", "true")
    get_settings.cache_clear()
    assert create_app() is not None
    get_settings.cache_clear()


def test_protected_env_rejects_non_atomic_supabase_store(monkeypatch):
    """The Supabase REST store's send-claim isn't atomic across replicas, so a
    prod deploy that selects it must fail the boot gate."""
    from app.api.main import create_app
    from app.config import get_settings

    for k, v in {
        "ENVIRONMENT": "production",
        "AUTH_ENABLED": "true",
        "CORS_ALLOW_ORIGINS": "https://app.example.com",
        "COMMS_DRYRUN": "true",
        "RUN_QUEUE_ENABLED": "true",
        "RUN_STORE_BACKEND": "supabase",  # the only remaining problem
    }.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="supabase"):
        create_app()

    # Switching to the atomic DB store clears the gate.
    monkeypatch.setenv("RUN_STORE_BACKEND", "db")
    get_settings.cache_clear()
    assert create_app() is not None
    get_settings.cache_clear()


# --------------------------------------------------------------------------- #
# Health / readiness probes
# --------------------------------------------------------------------------- #


def test_healthz_and_readyz(mock_mode):
    from fastapi.testclient import TestClient

    from app.api.main import app

    client = TestClient(app)
    assert client.get("/healthz").json() == {"status": "ok"}

    r = client.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["checks"]["run_store"].startswith("ok:")


# --------------------------------------------------------------------------- #
# Metrics + AI cost
# --------------------------------------------------------------------------- #


def test_estimate_cost_usd():
    from app.observability import estimate_cost_usd

    # 1M input + 1M output on opus = 15 + 75
    assert estimate_cost_usd("claude-opus-4-7", 1_000_000, 1_000_000) == pytest.approx(90.0)
    # mock / unknown models are free
    assert estimate_cost_usd("mock-classify", 1000, 1000) == 0.0


def test_metrics_endpoint_records_usage(mock_mode):
    from fastapi.testclient import TestClient

    from app.api.main import app
    from app.observability import metrics as m

    m.reset()
    m.record_ai_usage(provider="anthropic", model="claude-opus-4-7", input_tokens=1000, output_tokens=500)
    m.record_run(status="AWAITING_REVIEW", duration_ms=123.0)

    text = TestClient(app).get("/metrics").text
    assert "ap_ai_calls_total" in text
    assert 'provider="anthropic"' in text
    assert "ap_ai_cost_usd_total" in text
    assert "ap_runs_total" in text


# --------------------------------------------------------------------------- #
# Rules engine — specific routing (not just the catch-all)
# --------------------------------------------------------------------------- #


def test_rules_engine_routes_by_exception_type():
    from app.config import get_settings
    from app.rules.engine import RulesEngine

    eng = RulesEngine.from_path(get_settings().rules_policy_path)

    # Small, sub-2% price variance under $10k → auto-approve.
    d = eng.evaluate(
        _row(amount="5000", desc="Invoice exceeds PO by 1%"),
        _classification(conf=0.9),
    )
    assert d.resolution_path == ResolutionPath.AUTO_APPROVE
    assert d.rule_id == "pv_auto_approve_small"

    # Material (>=5%) price variance → escalate to controller.
    d = eng.evaluate(_row(desc="12% variance"), _classification())
    assert d.resolution_path == ResolutionPath.ESCALATE_CONTROLLER

    # Missing PO → request PO from vendor.
    d = eng.evaluate(
        _row(etype="Missing PO", desc="No PO on file"),
        _classification(etype=PrimaryExceptionType.MISSING_PO),
    )
    assert d.resolution_path == ResolutionPath.REQUEST_PO

    # Low confidence on a type with no earlier-matching rule ("Other") routes
    # to manual review via the confidence floor (before the final catch-all).
    d = eng.evaluate(
        _row(etype="Misc", desc="unclear"),
        _classification(etype=PrimaryExceptionType.OTHER, conf=0.4),
    )
    assert d.rule_id == "low_confidence_manual"


def test_rules_engine_is_deterministic():
    from app.config import get_settings
    from app.rules.engine import RulesEngine

    eng = RulesEngine.from_path(get_settings().rules_policy_path)
    row, c = _row(), _classification()
    assert eng.evaluate(row, c).rule_id == eng.evaluate(row, c).rule_id


def test_materiality_ceiling_overrides_auto_approve():
    """A high-value invoice must never auto-approve, even when a rule says so."""
    from decimal import Decimal

    from app.rules.engine import Policy, RulesEngine

    # A deliberately too-lenient policy: auto-approve ANY price variance.
    policy = Policy.model_validate(
        {
            "version": "test.1",
            "rules": [
                {
                    "id": "pv_auto_all",
                    "when": {"exception_type": "Price Variance"},
                    "then": {
                        "resolution_path": "AUTO_APPROVE",
                        "requires_communication": False,
                        "sla_hours": 24,
                    },
                },
                {"id": "catch_all", "when": {}, "then": {
                    "resolution_path": "MANUAL_REVIEW",
                    "requires_communication": False, "sla_hours": 72,
                }},
            ],
        }
    )
    eng = RulesEngine(policy)
    row = _row(amount="80000", desc="Invoice exceeds PO by 1%")
    c = _classification(conf=0.95)

    # Without the ceiling, the bad rule auto-approves an $80k invoice.
    assert eng.evaluate(row, c).resolution_path == ResolutionPath.AUTO_APPROVE

    # With a $25k ceiling, the guardrail overrides it to manual review.
    d = eng.evaluate(row, c, auto_approve_ceiling=Decimal("25000"))
    assert d.resolution_path == ResolutionPath.MANUAL_REVIEW
    assert d.requires_communication is False
    assert "materiality_ceiling" in d.rule_id
    assert any("CEILING" in line for line in d.rule_trace)

    # A small invoice under the ceiling still auto-approves.
    small = _row(amount="4000", desc="Invoice exceeds PO by 1%")
    assert (
        eng.evaluate(small, c, auto_approve_ceiling=Decimal("25000")).resolution_path
        == ResolutionPath.AUTO_APPROVE
    )


# --------------------------------------------------------------------------- #
# In-memory store mutation + readiness ping
# --------------------------------------------------------------------------- #


def test_in_memory_store_patch_and_ping():
    from app.api.store import RunStore

    store = RunStore()
    store.ping()  # never raises
    state = initial_state("run_s", "t")
    state["drafts"] = [
        CommunicationDraft(
            invoice_id="INV-1",
            channel=CommChannel.VENDOR_EMAIL,
            recipient_hint="Vendor AR contact",
            subject="s",
            body="b",
            template_id="t",
            model_id="m",
        )
    ]
    store.put(state)

    assert store.patch_draft("run_s", "INV-1", subject="new", body="newbody")
    got = store.get("run_s")
    assert got is not None
    draft = got["drafts"][0]
    assert draft.body == "newbody" and draft.is_edited_by_human

    assert store.update_draft_send_result(
        "run_s", "INV-1", send_status=SendStatus.SENT, send_provider="gmail",
        send_message_id="<id>", recipient="v@x.com", sent_at=datetime.now(UTC),
    )
    assert store.get("run_s")["drafts"][0].send_status == SendStatus.SENT
    # Unknown ids return False, never raise.
    assert not store.patch_draft("nope", "INV-1", subject=None, body="x")


# --------------------------------------------------------------------------- #
# Vendor master recipient lookup
# --------------------------------------------------------------------------- #


def test_vendor_master_lookup(tmp_path):
    from app.comms import recipients
    from app.config import Settings

    csv_path = tmp_path / "vendors.csv"
    csv_path.write_text("vendor_name,email\nWorkday,ar@workday.com\nOracle,billing@oracle.com\n",
                        encoding="utf-8")
    recipients._load_vendor_master.cache_clear()
    settings = Settings(vendor_master_path=csv_path, comms_test_recipient="fallback@test.com")

    draft = CommunicationDraft(
        invoice_id="INV-1", channel=CommChannel.VENDOR_EMAIL,
        recipient_hint="Vendor AR contact", body="b", template_id="t", model_id="m",
    )
    # Known vendor → its AR email.
    assert recipients.resolve_recipient(draft=draft, settings=settings, vendor_name="Workday") \
        == "ar@workday.com"
    # Unknown vendor with a configured master → refuse (None), don't mis-deliver.
    assert recipients.resolve_recipient(draft=draft, settings=settings, vendor_name="Unknown Inc") \
        is None


def test_recipient_falls_back_to_test_recipient_without_master():
    from app.comms import recipients
    from app.config import Settings

    settings = Settings(vendor_master_path=None, comms_test_recipient="safe@test.com")
    draft = CommunicationDraft(
        invoice_id="INV-1", channel=CommChannel.VENDOR_EMAIL,
        recipient_hint="Vendor AR contact", body="b", template_id="t", model_id="m",
    )
    assert recipients.resolve_recipient(draft=draft, settings=settings) == "safe@test.com"


# --------------------------------------------------------------------------- #
# Per-domain daily cap
# --------------------------------------------------------------------------- #


def test_comms_daily_cap_blocks_after_limit(monkeypatch, tmp_path):
    monkeypatch.setenv("COMMS_DRYRUN", "false")
    monkeypatch.setenv("COMMS_TEST_RECIPIENT", "vendor@example.com")
    monkeypatch.setenv("COMMS_ALLOWED_DOMAINS", "")  # allow all
    monkeypatch.setenv("COMMS_PER_DOMAIN_DAILY_CAP", "1")
    monkeypatch.setenv("GMAIL_SMTP_USER", "agent@example.com")
    monkeypatch.setenv("DB_PERSISTENCE_ENABLED", "false")  # exercise the in-process cap
    from app.config import get_settings
    get_settings.cache_clear()

    import app.comms.dispatcher as disp
    disp.reset_domain_cap()
    monkeypatch.setattr(
        disp, "send_email_via_gmail",
        lambda *, draft, recipient, settings, bcc: ("<id>", "ok"),
    )

    def _draft(i):
        return CommunicationDraft(
            invoice_id=f"INV-{i}", channel=CommChannel.VENDOR_EMAIL,
            recipient_hint="Vendor AR contact", subject="s", body="b",
            template_id="vendor_price_variance", model_id="m",
        )

    first = disp.dispatch(draft=_draft(1), run_id="run_cap")
    assert first.status == SendStatus.SENT
    second = disp.dispatch(draft=_draft(2), run_id="run_cap")
    assert second.status == SendStatus.SKIPPED
    assert "cap" in (second.error_message or "").lower()


# --------------------------------------------------------------------------- #
# AI nodes (mock mode) + PII redaction
# --------------------------------------------------------------------------- #


def test_classify_node_mock(mock_mode):
    from app.graph.nodes.classify import classify_node

    state = initial_state("run_c", "t")
    state["rows"] = [_row(etype="Missing PO", desc="No PO referenced")]
    out = classify_node(state)
    assert len(out["classifications"]) == 1
    c = out["classifications"][0]
    assert c.invoice_id == "INV-1"
    assert c.primary_exception_type == PrimaryExceptionType.MISSING_PO


def test_draft_node_mock_and_redaction(mock_mode):
    from app.graph.nodes.draft import draft_node

    state = initial_state("run_d", "t")
    state["rows"] = [_row()]
    state["classifications"] = [_classification()]
    state["resolutions"] = [
        ResolutionDecision(
            invoice_id="INV-1",
            resolution_path=ResolutionPath.MANUAL_REVIEW,
            rule_id="pv_manual_default",
            rule_version="v1",
            rule_trace=["t"],
            requires_communication=True,
            sla_hours=24,
        )
    ]
    out = draft_node(state)
    assert len(out["drafts"]) == 1
    assert out["drafts"][0].invoice_id == "INV-1"


def test_pii_redaction_helper():
    from app.graph.nodes.draft import _redact

    assert "[REDACTED]" in _redact("SSN 123-45-6789 here")
    assert "[REDACTED]" in _redact("card 4111111111111111")
    assert _redact("nothing sensitive") == "nothing sensitive"
