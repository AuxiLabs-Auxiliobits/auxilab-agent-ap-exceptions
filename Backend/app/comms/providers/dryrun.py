"""Dry-run provider — writes drafts to disk instead of sending.

The file layout under `artifacts/sent/{run_id}/`:
  <invoice_id>__<channel>.json   — full draft payload + resolved recipient
  <invoice_id>__<channel>.eml    — RFC-5322 .eml (for email channels), openable in Outlook/Apple Mail/Thunderbird

The .eml shape is intentional — reviewers can open it locally to preview
exactly what would have been sent without needing to flip the real-send
switch.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path

from app.comms.email_template import render_html, render_text
from app.config import Settings, get_settings
from app.schemas import CommChannel, CommunicationDraft

log = logging.getLogger("ap_agent.comms.dryrun")


def send_dryrun(
    *,
    draft: CommunicationDraft,
    recipient: str,
    run_id: str,
    sent_dir: Path,
    sender: str,
    bcc: str | None,
    settings: Settings | None = None,
    attachments: list | None = None,
) -> tuple[str, Path]:
    """Persist a dry-run record. Returns (message_id, file_path).

    ``settings`` should be the dispatcher's tenant-resolved Settings so the
    preview's signature/branding/HTML toggle match what a live send for that
    tenant would produce; falls back to env settings if not supplied."""
    out_dir = sent_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    msg_id = f"dryrun-{uuid.uuid4().hex[:12]}"
    base = out_dir / f"{draft.invoice_id}__{draft.channel.value}"

    settings = settings or get_settings()

    # Channel-aware preview: finance_note / slack go to Slack *only if* Slack is
    # connected in the resolved settings — otherwise they degrade to email. The
    # dry-run mirrors that exactly, so the preview shows the real target (it used
    # to always render an email, hiding the Slack routing).
    to_slack = draft.channel in (CommChannel.SLACK, CommChannel.FINANCE_NOTE) and bool(
        getattr(settings, "slack_bot_token", "") or getattr(settings, "slack_webhook_url", "")
    )
    slack_channel = (
        getattr(settings, "slack_channel", "")
        or getattr(settings, "slack_default_channel", "")
        or "#ap-escalations"
    )
    resolved_target = f"slack {slack_channel}" if to_slack else f"email {recipient}"

    payload = {
        "message_id": msg_id,
        "run_id": run_id,
        "invoice_id": draft.invoice_id,
        "channel": draft.channel.value,
        "resolved_target": resolved_target,
        "sender": sender,
        "recipient": recipient,
        "bcc": bcc,
        "subject": draft.subject,
        "body": draft.body,
        "template_id": draft.template_id,
        "model_id": draft.model_id,
        "is_edited_by_human": draft.is_edited_by_human,
        "captured_at": datetime.now(UTC).isoformat(),
    }
    base.with_suffix(".json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )

    if to_slack:
        # Slack-shaped preview: the channel + mrkdwn that would be posted.
        from app.comms.providers.slack_webhook import _to_mrkdwn

        slack_preview = (
            f"Slack dry-run preview → {slack_channel}\n"
            f"{draft.subject or draft.invoice_id}\n\n"
            f"{_to_mrkdwn(draft.body)}"
        )
        base.with_suffix(".slack.txt").write_text(slack_preview, encoding="utf-8")
    elif draft.channel in (
        CommChannel.VENDOR_EMAIL,
        CommChannel.INTERNAL_EMAIL,
        CommChannel.FINANCE_NOTE,
        CommChannel.SLACK,
    ):
        # Email-shaped: a full multipart .eml + standalone .html preview.
        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = recipient
        if bcc:
            msg["Bcc"] = bcc
        msg["Subject"] = draft.subject or f"AP exception {draft.invoice_id}"
        msg["X-AP-Agent-Message-ID"] = msg_id
        msg["X-AP-Agent-Run-ID"] = run_id
        text_body = render_text(draft, settings)
        msg.set_content(text_body)
        if settings.comms_email_html_enabled:
            html_body = render_html(draft, settings)
            msg.add_alternative(html_body, subtype="html")
            base.with_suffix(".html").write_text(html_body, encoding="utf-8")
        for att in attachments or []:
            msg.add_attachment(
                att.data, maintype=att.maintype, subtype=att.subtype, filename=att.filename
            )
            (out_dir / att.filename).write_bytes(att.data)
        base.with_suffix(".eml").write_bytes(bytes(msg))

    log.info(
        "dryrun: wrote %s (channel=%s recipient=%s)",
        base,
        draft.channel.value,
        recipient,
    )
    return msg_id, base


def write_consolidated_preview(
    *,
    subject: str,
    text: str,
    html: str | None,
    recipient: str,
    bcc: str | None,
    run_id: str,
    sent_dir: Path,
    sender: str,
    invoice_ids: list[str],
    attachments: list | None = None,
) -> tuple[str, Path]:
    """Persist a dry-run preview for a consolidated multi-invoice email. Returns
    (message_id, file_path). Writes .json + .eml (+ .html) so a reviewer can open
    exactly what would have gone out."""
    out_dir = sent_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    msg_id = f"dryrun-bulk-{uuid.uuid4().hex[:12]}"
    base = out_dir / f"consolidated__{msg_id}"

    base.with_suffix(".json").write_text(
        json.dumps(
            {
                "message_id": msg_id,
                "run_id": run_id,
                "recipient": recipient,
                "bcc": bcc,
                "subject": subject,
                "invoice_ids": invoice_ids,
                "captured_at": datetime.now(UTC).isoformat(),
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    if bcc:
        msg["Bcc"] = bcc
    msg["Subject"] = subject
    msg["X-AP-Agent-Message-ID"] = msg_id
    msg["X-AP-Agent-Run-ID"] = run_id
    msg["X-AP-Agent-Invoice-Count"] = str(len(invoice_ids))
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
        base.with_suffix(".html").write_text(html, encoding="utf-8")
    # Attach to the .eml AND drop each attachment as its own file so a reviewer
    # can open exactly what would have been sent (e.g. the invoices .xlsx).
    for att in attachments or []:
        msg.add_attachment(
            att.data, maintype=att.maintype, subtype=att.subtype, filename=att.filename
        )
        (out_dir / att.filename).write_bytes(att.data)
    base.with_suffix(".eml").write_bytes(bytes(msg))

    log.info(
        "dryrun: wrote consolidated %s (recipient=%s invoices=%d attachments=%d)",
        base, recipient, len(invoice_ids), len(attachments or []),
    )
    return msg_id, base
