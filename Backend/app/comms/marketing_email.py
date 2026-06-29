"""HTML email templates for the public marketing surface.

Covers: subscriber welcome, contact-us auto-reply, the bulk newsletter, and the
internal notifications you receive. All share one branded shell (brand color +
logo + signature, same knobs as the AP comms templates) and every bulk/opt-in
email carries an unsubscribe link.
"""
from __future__ import annotations

from html import escape

from app.comms.email_template import _paragraphs_to_html, _render_signature_html
from app.config import Settings


def _brand_color(s: Settings) -> str:
    c = (s.comms_brand_color or "").strip()
    return c if c.startswith("#") else "#1f4e79"


def _logo_html(s: Settings) -> str:
    url = (s.comms_logo_url or "").strip()
    if url.startswith(("http://", "https://")):
        return (
            f'<img src="{escape(url)}" alt="{escape(s.comms_signature_company)}" '
            'height="24" style="height:24px; margin-right:10px; vertical-align:middle;"/>'
        )
    return ""


def _wrap(*, label: str, body_html: str, settings: Settings, unsubscribe_url: str | None = None) -> str:
    color = _brand_color(settings)
    company = escape(settings.comms_signature_company)
    unsub = ""
    if unsubscribe_url:
        unsub = (
            '<tr><td style="padding:12px 24px; background:#f9fafb; '
            'border-top:1px solid #e5e7eb; color:#6b7280; font-size:11px; line-height:1.5;">'
            f"You are receiving this because you signed up at {company}. "
            f'<a href="{escape(unsubscribe_url)}" style="color:#6b7280;">Unsubscribe</a>.'
            "</td></tr>"
        )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/></head>
<body style="margin:0;padding:0;font-family:-apple-system,Segoe UI,Arial,Helvetica,sans-serif;background:#f4f6f8;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f4f6f8;padding:24px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08);max-width:600px;">
  <tr><td style="background:{color};color:#ffffff;padding:14px 24px;font-size:13px;letter-spacing:0.6px;text-transform:uppercase;font-weight:600;">
    {_logo_html(settings)}{escape(label)}
  </td></tr>
  <tr><td style="padding:24px;font-size:14px;color:#1f2937;line-height:1.55;">
    {body_html}
  </td></tr>
  <tr><td style="padding:0 24px 22px 24px;">{_render_signature_html(settings)}</td></tr>
  {unsub}
</table>
</td></tr></table>
</body></html>"""


# --------------------------------------------------------------------------- #
# Subscriber welcome
# --------------------------------------------------------------------------- #
def welcome(email: str, unsubscribe_url: str, settings: Settings) -> tuple[str, str, str]:
    company = settings.comms_signature_company
    subject = f"Welcome to the {company} newsletter"
    body = (
        "Thanks for subscribing — you're on the list.\n\n"
        "We'll send occasional product updates and finance-ops tips. "
        "You can unsubscribe at any time."
    )
    html = _wrap(label="Newsletter", body_html=_paragraphs_to_html(body), settings=settings, unsubscribe_url=unsubscribe_url)
    text = f"{body}\n\nUnsubscribe: {unsubscribe_url}\n"
    return subject, html, text


# --------------------------------------------------------------------------- #
# Contact-us auto-reply (to the submitter)
# --------------------------------------------------------------------------- #
def contact_ack(name: str, settings: Settings) -> tuple[str, str, str]:
    company = settings.comms_signature_company
    subject = f"We received your message — {company}"
    greeting = f"Hi {name}," if name.strip() else "Hi,"
    body = (
        f"{greeting}\n\n"
        f"Thanks for reaching out to {company}. We've received your message and "
        f"a member of our team will get back to you shortly.\n\n"
        f"This is an automated confirmation — no need to reply."
    )
    html = _wrap(label="Thanks for contacting us", body_html=_paragraphs_to_html(body), settings=settings)
    text = body
    return subject, html, text


# --------------------------------------------------------------------------- #
# Newsletter (bulk) — wraps operator-supplied content + unsubscribe
# --------------------------------------------------------------------------- #
def newsletter(subject: str, body: str, unsubscribe_url: str, settings: Settings) -> tuple[str, str]:
    html = _wrap(label="Newsletter", body_html=_paragraphs_to_html(body), settings=settings, unsubscribe_url=unsubscribe_url)
    text = f"{body}\n\nUnsubscribe: {unsubscribe_url}\n"
    return html, text


# --------------------------------------------------------------------------- #
# Internal notifications (to your inbox)
# --------------------------------------------------------------------------- #
def internal_contact(name: str, email: str, subj: str, message: str, settings: Settings) -> tuple[str, str, str]:
    subject = f"[Contact] {subj or 'Website enquiry'}"
    meta = f"From: {name or 'Anonymous'}" + (f" <{email}>" if email else "")
    body = f"{meta}\n\n{message}"
    html = _wrap(label="New contact enquiry", body_html=_paragraphs_to_html(body), settings=settings)
    return subject, html, body


def internal_subscriber(email: str, settings: Settings) -> tuple[str, str, str]:
    subject = "[Newsletter] New subscriber"
    body = f"New newsletter signup: {email}"
    html = _wrap(label="New subscriber", body_html=_paragraphs_to_html(body), settings=settings)
    return subject, html, body
