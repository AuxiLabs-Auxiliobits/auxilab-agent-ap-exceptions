"""Gmail send via the Gmail API (OAuth), mirroring gmail_smtp.send_email_via_gmail.

Used when an org connected Gmail via OAuth (a stored refresh token) instead of an
SMTP app password. Builds the same templated message and POSTs it to the Gmail
REST API with a freshly-minted access token. httpx only — no Google SDK.
"""
from __future__ import annotations

import base64
import logging
import uuid
from email.message import EmailMessage

import httpx

from app.comms.email_template import render_html, render_text
from app.comms.oauth import OAuthError, google_access_token
from app.comms.providers.gmail_smtp import GmailSendError
from app.config import Settings
from app.schemas import CommunicationDraft

log = logging.getLogger("ap_agent.comms.gmail_oauth")

_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


def send_email_via_gmail_oauth(
    *,
    draft: CommunicationDraft,
    recipient: str,
    settings: Settings,
    bcc: str | None,
) -> tuple[str, str]:
    """Send the draft via the Gmail API using the org's OAuth refresh token."""
    if not settings.gmail_oauth_refresh_token:
        raise GmailSendError("No Gmail OAuth refresh token for this org.")
    try:
        access_token = google_access_token(settings, settings.gmail_oauth_refresh_token)
    except OAuthError as e:
        raise GmailSendError(str(e)) from e

    msg_id = f"<{uuid.uuid4().hex}@ap-exception-agent>"
    msg = EmailMessage()
    msg["Message-ID"] = msg_id
    # From defaults to the authorized account; gmail_smtp_user carries it for OAuth too.
    if settings.gmail_smtp_user:
        msg["From"] = settings.gmail_smtp_user
    msg["To"] = recipient
    if bcc:
        msg["Bcc"] = bcc
    if settings.comms_ap_team_mailbox:
        msg["Reply-To"] = settings.comms_ap_team_mailbox
    msg["Subject"] = draft.subject or f"AP exception {draft.invoice_id}"
    msg.set_content(render_text(draft, settings))
    if settings.comms_email_html_enabled:
        msg.add_alternative(render_html(draft, settings), subtype="html")

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    try:
        resp = httpx.post(
            _SEND_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            json={"raw": raw},
            timeout=30.0,
        )
    except httpx.HTTPError as e:
        raise GmailSendError(f"Gmail API network error: {e}") from e
    if resp.status_code >= 300:
        raise GmailSendError(f"Gmail API send failed: {resp.status_code} {resp.text[:200]}")
    log.info("gmail_oauth: sent invoice=%s to=%s message_id=%s", draft.invoice_id, recipient, msg_id)
    return msg_id, "250 OK"


def send_prebuilt_via_gmail_oauth(
    *,
    to: str,
    subject: str,
    text: str,
    html: str | None,
    settings: Settings,
    bcc: str | None = None,
    reply_to: str | None = None,
    attachments: list | None = None,
) -> tuple[str, str]:
    """Send a pre-rendered email (subject + text/html) via the Gmail API. Mirrors
    send_email_via_gmail_oauth but isn't bound to a single CommunicationDraft —
    used for the consolidated multi-invoice email."""
    if not settings.gmail_oauth_refresh_token:
        raise GmailSendError("No Gmail OAuth refresh token for this org.")
    try:
        access_token = google_access_token(settings, settings.gmail_oauth_refresh_token)
    except OAuthError as e:
        raise GmailSendError(str(e)) from e

    msg_id = f"<{uuid.uuid4().hex}@ap-exception-agent>"
    msg = EmailMessage()
    msg["Message-ID"] = msg_id
    if settings.gmail_smtp_user:
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
    for att in attachments or []:
        msg.add_attachment(
            att.data, maintype=att.maintype, subtype=att.subtype, filename=att.filename
        )

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    try:
        resp = httpx.post(
            _SEND_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            json={"raw": raw},
            timeout=30.0,
        )
    except httpx.HTTPError as e:
        raise GmailSendError(f"Gmail API network error: {e}") from e
    if resp.status_code >= 300:
        raise GmailSendError(f"Gmail API send failed: {resp.status_code} {resp.text[:200]}")
    log.info("gmail_oauth: sent consolidated to=%s message_id=%s", to, msg_id)
    return msg_id, "250 OK"
