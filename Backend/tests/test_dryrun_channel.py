"""Dry-run previews are channel-aware: a finance/escalation note posts to Slack
when Slack is connected, and degrades to email otherwise — and the preview shows
the real target either way."""
from __future__ import annotations

import json


def _draft():
    from app.schemas import CommChannel, CommunicationDraft

    return CommunicationDraft(
        invoice_id="INV-1",
        channel=CommChannel.FINANCE_NOTE,
        recipient_hint="Finance Controller",
        subject="Escalation",
        body="**Exposure:** $182,400",
        template_id="t",
        model_id="m",
    )


def test_slack_card_shows_friendly_recommended_approach():
    """The Slack escalation card surfaces the resolution path as the friendly
    'Recommended approach' label, not the raw routing code."""
    from app.comms.providers.slack_webhook import _build_blocks

    ctx = {"vendor_name": "Acme", "resolution_path": "ESCALATE_CONTROLLER"}
    texts = [
        f.get("text", "")
        for b in _build_blocks(_draft(), ctx)
        for f in b.get("fields", [])
    ]
    blob = "\n".join(texts)
    assert "*Recommended approach:*\nEscalate to Controller" in blob
    assert "ESCALATE_CONTROLLER" not in blob
    assert "*Resolution:*" not in blob


def test_slack_context_emits_raw_code_and_renders_canonical_label():
    """End-to-end: _slack_context carries the RAW routing code and the Slack
    renderer turns it into the canonical 'Recommended approach' label. Guards the
    real send path (the unit test above feeds _build_blocks a raw code directly)."""
    from app.api.routes_comms import _slack_context
    from app.comms.providers.slack_webhook import _build_blocks
    from app.schemas import ExceptionRow, ResolutionDecision, ResolutionPath
    from decimal import Decimal

    state = {
        "rows": [ExceptionRow(
            invoice_id="INV-1", vendor_name="Acme", invoice_amount=Decimal("1000"),
            po_number="PO-1", exception_type="Price Variance",
            exception_description="x", days_outstanding=5,
        )],
        "classifications": [],
        "resolutions": [ResolutionDecision(
            invoice_id="INV-1", resolution_path=ResolutionPath.ESCALATE_CONTROLLER,
            rule_id="r", rule_version="v1", rule_trace=["t"],
            requires_communication=True, sla_hours=8,
        )],
    }
    ctx = _slack_context(state, "INV-1")
    assert ctx["resolution_path"] == "ESCALATE_CONTROLLER"  # raw, not pre-titled

    texts = [
        f.get("text", "")
        for b in _build_blocks(_draft(), ctx)
        for f in b.get("fields", [])
    ]
    blob = "\n".join(texts)
    assert "Escalate to Controller" in blob       # canonical label
    assert "Escalate Controller" not in blob      # not the old .title() form


def test_finance_note_previews_as_slack_when_connected(tmp_path):
    from app.comms.providers.dryrun import send_dryrun
    from app.config import Settings

    s = Settings(slack_webhook_url="https://hooks.slack.test/x", slack_channel="#ap-escalations")
    _msg, base = send_dryrun(
        draft=_draft(), recipient="ctrl@example.com", run_id="r",
        sent_dir=tmp_path, sender="ap@example.com", bcc=None, settings=s,
    )

    assert base.with_suffix(".slack.txt").exists()      # Slack-shaped preview
    assert not base.with_suffix(".eml").exists()         # NOT an email
    payload = json.loads(base.with_suffix(".json").read_text(encoding="utf-8"))
    assert payload["resolved_target"].startswith("slack")
    assert "#ap-escalations" in payload["resolved_target"]


def test_finance_note_degrades_to_email_without_slack(tmp_path):
    from app.comms.providers.dryrun import send_dryrun
    from app.config import Settings

    s = Settings(slack_webhook_url="", slack_bot_token="")
    _msg, base = send_dryrun(
        draft=_draft(), recipient="ctrl@example.com", run_id="r",
        sent_dir=tmp_path, sender="ap@example.com", bcc=None, settings=s,
    )

    assert base.with_suffix(".eml").exists()             # email fallback
    assert not base.with_suffix(".slack.txt").exists()
    payload = json.loads(base.with_suffix(".json").read_text(encoding="utf-8"))
    assert payload["resolved_target"].startswith("email")
