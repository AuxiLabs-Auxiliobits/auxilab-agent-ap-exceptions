"""Operator SLA-digest notifier (F1-2).

Sends the AP team an internal summary of what's waiting / breaching SLA — a
different audience from the vendor/internal *invoice* comms the dispatcher
handles, so it does not go through the per-domain cap or vendor allowlist.
Reuses the email provider + dry-run preview path and honors COMMS_DRYRUN, so a
digest is never sent live until comms are switched on.
"""
from __future__ import annotations

import logging

from app.comms.providers.dryrun import send_dryrun
from app.comms.providers.gmail_smtp import send_email_via_gmail
from app.config import Settings
from app.schemas import CommChannel, CommunicationDraft, resolution_path_label

log = logging.getLogger("ap_agent.comms.operator")


def _operator_recipient(settings: Settings) -> str | None:
    """Internal AP operations mailbox the digest is sent to."""
    return (
        settings.comms_ap_team_mailbox
        or settings.comms_finance_controller_mailbox
        or settings.gmail_smtp_user
        or None
    )


def _subject(run_id: str, report: dict) -> str:
    return (
        f"[AP SLA] {report['breached']} past SLA, "
        f"{report['high_waiting']} HIGH waiting (run {run_id[:8]})"
    )


def _body(run_id: str, report: dict, *, include_breakdown: bool = True) -> str:
    lines = [
        f"AP exception SLA digest for run {run_id}.",
        "",
        f"Open items: {report['total_open']}",
        f"HIGH priority waiting: {report['high_waiting']}",
        f"Past SLA (breached): {report['breached']}",
        f"Due soon: {report['due_soon']}",
    ]
    cases = report.get("cases")
    if cases:
        lines.append(
            f"Cases — in progress: {cases['in_progress']} · "
            f"resolved/closed: {cases['resolved']} · "
            f"needs follow-up: {cases['needs_follow_up']}"
        )
    # Inline the most-overdue breakdown only when no spreadsheet is attached.
    # When the full list rides along as an .xlsx, the body stays a short overview
    # + a pointer to the attachment — no point re-listing every invoice.
    if include_breakdown and report["breached_items"]:
        lines += ["", "Breached (most overdue first):"]
        for i in report["breached_items"][:15]:
            amt = (
                f"${i['invoice_amount']:,.0f}"
                if i.get("invoice_amount") is not None
                else "n/a"
            )
            lines.append(
                f"  - {i['invoice_id']} | {i.get('vendor_name') or 'unknown'} | {amt} | "
                f"{resolution_path_label(i.get('resolution_path'))} | "
                f"{i['hours_overdue']}h overdue (SLA {i['sla_hours']}h)"
            )
    return "\n".join(lines)


def send_sla_digest(*, run_id: str, report: dict, settings: Settings) -> dict:
    """Send (or dry-run) the operator SLA digest. Returns a small status dict;
    a no-op ``skipped`` when no operator mailbox is configured."""
    recipient = _operator_recipient(settings)
    if not recipient:
        return {
            "status": "skipped",
            "reason": "no operator mailbox configured (set COMMS_AP_TEAM_MAILBOX)",
        }

    # When there are many SLA items, attach the FULL list as a spreadsheet and
    # keep the body to a short overview — no inline invoice list — so the email
    # isn't a wall of text duplicating the attachment. Under the threshold there's
    # no attachment, so the body inlines the most-overdue breakdown instead.
    attachments = None
    items_total = len(report.get("breached_items") or []) + len(report.get("due_soon_items") or [])
    attaching = items_total > settings.comms_consolidated_attachment_threshold

    body = _body(run_id, report, include_breakdown=not attaching)

    if attaching:
        from app.comms.attachments import build_sla_digest_attachment

        att = build_sla_digest_attachment(report, run_id=run_id)
        attachments = [att]
        body += f"\n\nFull SLA list ({items_total} items) attached: {att.filename}\n"

    draft = CommunicationDraft(
        invoice_id=f"sla-digest-{run_id}",
        channel=CommChannel.INTERNAL_EMAIL,
        recipient_hint="AP operations team",
        subject=_subject(run_id, report),
        body=body,
        template_id="operator_sla_digest",
        model_id="system",
    )

    if settings.comms_dryrun:
        msg_id, _path = send_dryrun(
            draft=draft,
            recipient=recipient,
            run_id=run_id,
            sent_dir=settings.comms_sent_dir,
            sender=settings.gmail_smtp_user or "ap-agent@local",
            bcc=None,
            settings=settings,
            attachments=attachments,
        )
        return {"status": "dryrun", "recipient": recipient, "subject": draft.subject, "message_id": msg_id}

    msg_id, _resp = send_email_via_gmail(
        draft=draft, recipient=recipient, settings=settings, bcc=None, attachments=attachments,
    )
    log.info("operator: sent SLA digest for run=%s to %s", run_id, recipient)
    return {"status": "sent", "recipient": recipient, "subject": draft.subject, "message_id": msg_id}
