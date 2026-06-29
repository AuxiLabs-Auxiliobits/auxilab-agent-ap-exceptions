"""Gmail SMTP provider.

Setup (one-time, on the Gmail account you want to send as):
  1. Turn ON 2-Factor Authentication.
  2. Visit https://myaccount.google.com/apppasswords and generate a 16-char
     App Password. (Regular Gmail passwords no longer work for SMTP since 2022.)
  3. Set GMAIL_SMTP_USER + GMAIL_SMTP_PASSWORD in .env.

Limits to know:
  - Free Gmail: 100 external emails / day. 500 recipients / day.
  - Google Workspace: 2,000 external emails / day.
  - Sender address is fixed to the Gmail account (free) or any verified
    alias in the domain (Workspace).
"""
from __future__ import annotations

import logging
import smtplib
import ssl
import uuid
from email.message import EmailMessage

from app.comms.email_template import render_html, render_text
from app.config import Settings
from app.schemas import CommunicationDraft

log = logging.getLogger("ap_agent.comms.gmail")


class GmailSendError(RuntimeError):
    """Raised when SMTP refuses to send."""


def send_email_via_gmail(
    *,
    draft: CommunicationDraft,
    recipient: str,
    settings: Settings,
    bcc: str | None,
    attachments: list | None = None,
) -> tuple[str, str]:
    """Send the draft via Gmail SMTP. Returns (smtp_message_id, response_text)."""
    if not (settings.gmail_smtp_user and settings.gmail_smtp_password):
        raise GmailSendError(
            "Gmail SMTP credentials missing. Set GMAIL_SMTP_USER and "
            "GMAIL_SMTP_PASSWORD (App Password — NOT your account password)."
        )

    msg_id = f"<{uuid.uuid4().hex}@ap-exception-agent>"
    msg = EmailMessage()
    msg["Message-ID"] = msg_id
    msg["From"] = settings.gmail_smtp_user
    msg["To"] = recipient
    if bcc:
        msg["Bcc"] = bcc
    # Reply-To routes vendor replies to the human AP team, NOT to the bot.
    if settings.comms_ap_team_mailbox:
        msg["Reply-To"] = settings.comms_ap_team_mailbox
    msg["Subject"] = draft.subject or f"AP exception {draft.invoice_id}"
    msg["X-AP-Agent-Invoice-ID"] = draft.invoice_id
    msg["X-AP-Agent-Channel"] = draft.channel.value
    msg["X-AP-Agent-Template"] = draft.template_id

    # Always include the plain-text version (with signature appended) as the
    # primary body; add HTML as the alternative when enabled. This is the
    # canonical RFC-5322 multipart/alternative pattern — clients pick the
    # richest version they can render.
    text_body = render_text(draft, settings)
    msg.set_content(text_body)
    if settings.comms_email_html_enabled:
        html_body = render_html(draft, settings)
        msg.add_alternative(html_body, subtype="html")
    _add_attachments(msg, attachments)

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(
            settings.gmail_smtp_host, settings.gmail_smtp_port, timeout=30
        ) as s:
            s.ehlo()
            s.starttls(context=context)
            s.ehlo()
            s.login(settings.gmail_smtp_user, settings.gmail_smtp_password)
            refused = s.send_message(msg)
        if refused:
            raise GmailSendError(f"recipients refused: {refused}")
    except smtplib.SMTPAuthenticationError as e:
        raise GmailSendError(
            f"Gmail auth failed (code={e.smtp_code}). Did you use an App Password? "
            f"{e.smtp_error!r}"
        ) from e
    except smtplib.SMTPException as e:
        raise GmailSendError(f"SMTP error: {e}") from e

    log.info(
        "gmail: sent invoice=%s to=%s message_id=%s",
        draft.invoice_id,
        recipient,
        msg_id,
    )
    return msg_id, "250 OK"


def send_plain_email(
    *,
    to: str,
    subject: str,
    body: str,
    settings: Settings,
    reply_to: str | None = None,
) -> tuple[str, str]:
    """Send a plain-text email via SMTP (no draft/template).

    Used for non-pipeline mail such as the public contact form. Returns
    (smtp_message_id, response_text)."""
    if not (settings.gmail_smtp_user and settings.gmail_smtp_password):
        raise GmailSendError(
            "Gmail SMTP credentials missing. Set GMAIL_SMTP_USER and GMAIL_SMTP_PASSWORD."
        )
    msg_id = f"<{uuid.uuid4().hex}@ap-exception-agent>"
    msg = EmailMessage()
    msg["Message-ID"] = msg_id
    msg["From"] = settings.gmail_smtp_user
    msg["To"] = to
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Subject"] = subject
    msg.set_content(body)

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(settings.gmail_smtp_host, settings.gmail_smtp_port, timeout=30) as s:
            s.ehlo()
            s.starttls(context=context)
            s.ehlo()
            s.login(settings.gmail_smtp_user, settings.gmail_smtp_password)
            refused = s.send_message(msg)
        if refused:
            raise GmailSendError(f"recipients refused: {refused}")
    except smtplib.SMTPAuthenticationError as e:
        raise GmailSendError(f"Gmail auth failed (code={e.smtp_code}). Use an App Password.") from e
    except smtplib.SMTPException as e:
        raise GmailSendError(f"SMTP error: {e}") from e

    log.info("gmail: sent plain email to=%s message_id=%s", to, msg_id)
    return msg_id, "250 OK"


def _add_attachments(msg: EmailMessage, attachments: list | None) -> None:
    """Attach EmailAttachment items (filename/data/maintype/subtype) to a message."""
    for att in attachments or []:
        msg.add_attachment(
            att.data, maintype=att.maintype, subtype=att.subtype, filename=att.filename
        )


def _build_message(
    *,
    to: str,
    subject: str,
    text: str,
    html: str | None,
    settings: Settings,
    reply_to: str | None,
    bcc: str | None = None,
    attachments: list | None = None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["Message-ID"] = f"<{uuid.uuid4().hex}@ap-exception-agent>"
    msg["From"] = settings.gmail_smtp_user
    msg["To"] = to
    if bcc:
        msg["Bcc"] = bcc
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Subject"] = subject
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    _add_attachments(msg, attachments)
    return msg


def send_simple_email(
    *,
    to: str,
    subject: str,
    text: str,
    html: str | None = None,
    settings: Settings,
    reply_to: str | None = None,
    bcc: str | None = None,
    attachments: list | None = None,
) -> tuple[str, str]:
    """Send one email (text + optional HTML alternative + attachments) over its own connection."""
    if not (settings.gmail_smtp_user and settings.gmail_smtp_password):
        raise GmailSendError("Gmail SMTP credentials missing.")
    msg = _build_message(
        to=to, subject=subject, text=text, html=html, settings=settings,
        reply_to=reply_to, bcc=bcc, attachments=attachments,
    )
    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(settings.gmail_smtp_host, settings.gmail_smtp_port, timeout=30) as s:
            s.ehlo()
            s.starttls(context=context)
            s.ehlo()
            s.login(settings.gmail_smtp_user, settings.gmail_smtp_password)
            s.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise GmailSendError(f"Gmail auth failed (code={e.smtp_code}). Use an App Password.") from e
    except smtplib.SMTPException as e:
        raise GmailSendError(f"SMTP error: {e}") from e
    return msg["Message-ID"], "250 OK"


def send_bulk_emails(*, messages: list[dict], settings: Settings) -> list[dict]:
    """Send many emails over a SINGLE SMTP connection (efficient + throttle-friendly).

    Each item: {to, subject, text, html?, reply_to?}. Returns a per-recipient
    list of {to, ok, error?}. A single bad recipient never aborts the batch.
    """
    if not (settings.gmail_smtp_user and settings.gmail_smtp_password):
        raise GmailSendError("Gmail SMTP credentials missing.")
    results: list[dict] = []
    context = ssl.create_default_context()
    with smtplib.SMTP(settings.gmail_smtp_host, settings.gmail_smtp_port, timeout=60) as s:
        s.ehlo()
        s.starttls(context=context)
        s.ehlo()
        s.login(settings.gmail_smtp_user, settings.gmail_smtp_password)
        for m in messages:
            try:
                msg = _build_message(
                    to=m["to"], subject=m["subject"], text=m.get("text", ""),
                    html=m.get("html"), settings=settings, reply_to=m.get("reply_to"),
                )
                s.send_message(msg)
                results.append({"to": m["to"], "ok": True})
            except smtplib.SMTPException as e:
                log.warning("bulk send failed to=%s: %s", m.get("to"), e)
                results.append({"to": m["to"], "ok": False, "error": str(e)[:200]})
    return results
