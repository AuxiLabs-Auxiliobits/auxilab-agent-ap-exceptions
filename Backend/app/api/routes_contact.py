"""Public landing-page endpoints + newsletter.

- POST /v1/contact     contact form → emails your inbox (HTML) + auto-reply to sender
- POST /v1/subscribe   newsletter signup → stores the subscriber + welcome email
- GET  /v1/unsubscribe  one-click unsubscribe (token from the email footer)
- POST /v1/newsletter   bulk send to all active subscribers (token-gated, throttled)

Contact/subscribe are unauthenticated (signed-out landing page) and send via the
platform SMTP, honoring CONTACT_DRYRUN. The newsletter is platform-operator only,
protected by the NEWSLETTER_ADMIN_TOKEN header (not the org RBAC).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.api import subscribers
from app.comms import marketing_email
from app.comms.providers.gmail_smtp import GmailSendError, send_bulk_emails, send_simple_email
from app.config import get_settings

log = logging.getLogger("ap_agent.routes_contact")

router = APIRouter(prefix="/v1", tags=["contact"])


class ContactInput(BaseModel):
    name: str = Field(default="", max_length=200)
    email: str = Field(default="", max_length=320)
    subject: str = Field(default="", max_length=200)
    message: str = Field(default="", max_length=5000)
    company_website: str = ""  # honeypot


class SubscribeInput(BaseModel):
    email: str = Field(default="", max_length=320)
    company_website: str = ""  # honeypot


class NewsletterInput(BaseModel):
    subject: str = Field(max_length=200)
    body: str = Field(max_length=20000)
    dry_run: bool = False


class NewsletterPreviewInput(BaseModel):
    subject: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=20000)


def _require_newsletter_token(token: str) -> None:
    s = get_settings()
    if not s.newsletter_admin_token:
        raise HTTPException(403, "Newsletter sending is disabled (set NEWSLETTER_ADMIN_TOKEN).")
    if token != s.newsletter_admin_token:
        raise HTTPException(403, "Invalid newsletter token.")


def _smtp_ready(s) -> bool:
    return bool(s.gmail_smtp_user and s.gmail_smtp_password)


def _send(*, to: str, subject: str, html: str, text: str, reply_to: str | None = None) -> None:
    """Best-effort single send (used for welcome/ack/internal). Never raises."""
    try:
        send_simple_email(
            to=to, subject=subject, text=text, html=html,
            settings=get_settings(), reply_to=reply_to,
        )
    except GmailSendError as e:
        log.warning("marketing: send to %s failed: %s", to, e)


def _notify_lead_slack(s, *, name: str, email: str, intent: str, subject: str) -> None:
    """Best-effort real-time triage ping to the platform ops Slack webhook.

    No-op when SLACK_WEBHOOK_URL isn't configured; never raises into the request.
    """
    url = s.slack_webhook_url
    if not url:
        return
    try:
        import httpx

        who = (name or "").strip() or "Someone"
        line = f":inbox_tray: New *{intent}* lead — {who} <mailto:{email}|{email}>"
        if subject:
            line += f"\n> {subject}"
        httpx.post(url, json={"text": line}, timeout=8.0)
    except Exception:  # noqa: BLE001 — notification is best-effort
        log.warning("contact: slack lead ping failed", exc_info=True)


# --------------------------------------------------------------------------- #
# Contact form
# --------------------------------------------------------------------------- #
@router.post("/contact")
def contact(payload: ContactInput = Body(...)) -> dict:
    if payload.company_website.strip():
        return {"status": "ok"}  # honeypot
    if not payload.message.strip():
        raise HTTPException(422, "A message is required.")
    s = get_settings()

    # Persist the lead FIRST — a prospect must never be lost if email/SMTP fails
    # or the inbox is unmonitored. Best-effort: a storage hiccup must not 500 the
    # public form. ``intent`` (demo/pricing/support/general) tags it for triage.
    intent = "general"
    try:
        from app.api import leads

        _lead_id, intent = leads.add(
            name=payload.name,
            email=payload.email.strip(),
            subject=payload.subject.strip(),
            message=payload.message.strip(),
        )
    except Exception:  # noqa: BLE001 — persistence must not break the form
        log.exception("contact: failed to persist lead (continuing to notify)")
    # Real-time triage ping to the platform ops Slack (best effort, only if set).
    _notify_lead_slack(
        s, name=payload.name, email=payload.email.strip(),
        intent=intent, subject=payload.subject.strip(),
    )

    to = s.contact_to
    if not to:
        raise HTTPException(503, "Contact is not configured on the server.")

    subj, html, text = marketing_email.internal_contact(
        payload.name, payload.email.strip(), payload.subject.strip(), payload.message.strip(), s
    )
    if s.contact_dryrun:
        log.info("contact (CONTACT_DRYRUN): to=%s subject=%s", to, subj)
        return {"status": "ok", "delivered": False}
    if not _smtp_ready(s):
        raise HTTPException(503, "Contact email isn't configured (no SMTP).")

    reply_to = payload.email.strip() or None
    _send(to=to, subject=subj, html=html, text=text, reply_to=reply_to)
    # Auto-reply to the submitter (best effort).
    if reply_to:
        a_subj, a_html, a_text = marketing_email.contact_ack(payload.name.strip(), s)
        _send(to=reply_to, subject=a_subj, html=a_html, text=a_text)
    return {"status": "ok", "delivered": True}


# --------------------------------------------------------------------------- #
# Lead inbox (platform-operator only — reuses the newsletter operator token)
# --------------------------------------------------------------------------- #
@router.get("/leads/stats")
def leads_stats(x_newsletter_token: str = Header(default="")) -> dict:
    """Lead totals + intent breakdown for the operator console (token-gated)."""
    _require_newsletter_token(x_newsletter_token)
    from app.api import leads

    return leads.counts()


@router.get("/leads")
def list_leads(
    limit: int = Query(default=100, ge=1, le=1000),
    x_newsletter_token: str = Header(default=""),
) -> dict:
    """Newest-first captured leads for triage (token-gated)."""
    _require_newsletter_token(x_newsletter_token)
    from app.api import leads

    rows = leads.list_recent(limit)
    return {"leads": rows, "total": len(rows)}


# --------------------------------------------------------------------------- #
# Newsletter signup
# --------------------------------------------------------------------------- #
@router.post("/subscribe")
def subscribe(payload: SubscribeInput = Body(...)) -> dict:
    if payload.company_website.strip():
        return {"status": "ok"}  # honeypot
    email = payload.email.strip()
    if "@" not in email:
        raise HTTPException(422, "A valid email is required.")
    s = get_settings()
    # Always store the subscriber (the primary action).
    token, _created = subscribers.add(email, source="landing")

    if s.contact_dryrun or not _smtp_ready(s):
        log.info("subscribe (no send): %s stored", email)
        return {"status": "ok", "subscribed": True, "delivered": False}

    # Welcome email to the subscriber + internal notification (best effort).
    w_subj, w_html, w_text = marketing_email.welcome(email, subscribers.unsubscribe_url(token), s)
    _send(to=email, subject=w_subj, html=w_html, text=w_text)
    if s.contact_to:
        i_subj, i_html, i_text = marketing_email.internal_subscriber(email, s)
        _send(to=s.contact_to, subject=i_subj, html=i_html, text=i_text)
    return {"status": "ok", "subscribed": True, "delivered": True}


# --------------------------------------------------------------------------- #
# Unsubscribe (one-click, from the email footer link)
# --------------------------------------------------------------------------- #
@router.get("/unsubscribe", response_class=HTMLResponse)
def unsubscribe(token: str = Query(default="")) -> HTMLResponse:
    email = subscribers.unsubscribe_by_token(token.strip()) if token.strip() else None
    if email is None:
        msg = "This unsubscribe link is invalid or has already been used."
    else:
        msg = f"You ({email}) have been unsubscribed. You won't receive further newsletters."
    html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Unsubscribe</title></head>"
        "<body style='font-family:system-ui,sans-serif;background:#f4f6f8;'>"
        "<div style='max-width:480px;margin:80px auto;background:#fff;border-radius:8px;"
        "padding:32px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.08);'>"
        f"<h2 style='margin:0 0 12px;'>Unsubscribe</h2><p style='color:#4b5563;'>{msg}</p>"
        "</div></body></html>"
    )
    return HTMLResponse(content=html)


# --------------------------------------------------------------------------- #
# Newsletter bulk send (platform-operator only, token-gated)
# --------------------------------------------------------------------------- #
@router.get("/newsletter/stats")
def newsletter_stats(x_newsletter_token: str = Header(default="")) -> dict:
    """Subscriber counts for the admin composer (token-gated)."""
    _require_newsletter_token(x_newsletter_token)
    return subscribers.counts()


@router.post("/newsletter/preview")
def newsletter_preview(
    payload: NewsletterPreviewInput = Body(...),
    x_newsletter_token: str = Header(default=""),
) -> dict:
    """Render the newsletter HTML exactly as it will be sent (with a sample
    unsubscribe link). Nothing is sent."""
    _require_newsletter_token(x_newsletter_token)
    html, _text = marketing_email.newsletter(
        payload.subject or "(no subject)",
        payload.body or "(empty body)",
        subscribers.unsubscribe_url("sample-token"),
        get_settings(),
    )
    return {"html": html}


@router.post("/newsletter")
def send_newsletter(
    payload: NewsletterInput = Body(...),
    x_newsletter_token: str = Header(default=""),
) -> dict:
    s = get_settings()
    _require_newsletter_token(x_newsletter_token)

    active = subscribers.list_active()
    capped = active[: s.newsletter_max_per_send]
    if len(active) > len(capped):
        log.warning(
            "newsletter: %d subscribers exceeds cap %d — sending to first %d only",
            len(active), s.newsletter_max_per_send, len(capped),
        )

    if payload.dry_run or not _smtp_ready(s):
        return {"recipients": len(capped), "sent": 0, "failed": 0, "dry_run": True}

    messages = []
    for sub in capped:
        html, text = marketing_email.newsletter(
            payload.subject, payload.body, subscribers.unsubscribe_url(sub["unsubscribe_token"]), s
        )
        messages.append({"to": sub["email"], "subject": payload.subject, "text": text, "html": html})
    results = send_bulk_emails(messages=messages, settings=s)
    sent = sum(1 for r in results if r["ok"])
    return {
        "recipients": len(capped),
        "sent": sent,
        "failed": len(results) - sent,
        "capped_out": len(active) - len(capped),
    }
