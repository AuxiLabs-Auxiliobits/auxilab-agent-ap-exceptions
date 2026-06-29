"""Email template renderer — produces clean HTML + text from a CommunicationDraft.

The LLM produces the body content; THIS module produces the chrome around it
(header bar, structured layout, signature block, footer). Keeping the wrapper
out of the LLM ensures:
  - the signature is always present and consistent,
  - branding never gets hallucinated,
  - a config change updates every outgoing message instantly.

The HTML is intentionally inline-CSS-only and table-based — that's what
Gmail / Outlook / Apple Mail render reliably. No <style> blocks, no images
(avoids spam triggers + broken external assets), no JavaScript.
"""
from __future__ import annotations

import re
from html import escape

from app.config import Settings
from app.schemas import CommChannel, CommunicationDraft

# Channel → (header label, accent colour). Finance escalations get a red bar
# so a controller's inbox immediately telegraphs urgency.
_CHANNEL_PRESETS: dict[CommChannel, tuple[str, str]] = {
    CommChannel.VENDOR_EMAIL:   ("Vendor Communication",  "#1f4e79"),
    CommChannel.INTERNAL_EMAIL: ("Internal Notice",       "#374151"),
    CommChannel.SLACK:          ("Internal Notification", "#374151"),
    CommChannel.FINANCE_NOTE:   ("Finance Escalation",    "#b91c1c"),
}


_URL_RE = re.compile(r"(https?://[^\s<>]+)")


def _linkify(text: str) -> str:
    return _URL_RE.sub(r'<a href="\1" style="color:#1f4e79;">\1</a>', text)


def _paragraphs_to_html(body: str) -> str:
    """Convert the LLM's plain-text body to clean HTML.

    Heuristics:
      - Lines starting with '- ' or '* ' become a single <ul> until a blank
        line breaks the run.
      - Blank lines separate paragraphs.
      - URLs get linkified.
      - Everything is HTML-escaped first.
    """
    body = body.replace("\r\n", "\n").strip()
    if not body:
        return ""

    out_blocks: list[str] = []
    in_list = False
    list_items: list[str] = []
    para_lines: list[str] = []

    def flush_list():
        nonlocal in_list, list_items
        if list_items:
            items_html = "".join(
                f'<li style="margin:4px 0;">{_linkify(escape(li))}</li>'
                for li in list_items
            )
            out_blocks.append(
                f'<ul style="margin:8px 0; padding-left:20px; color:#1f2937;">'
                f"{items_html}</ul>"
            )
            list_items = []
        in_list = False

    def flush_para():
        nonlocal para_lines
        if para_lines:
            joined = "<br/>".join(_linkify(escape(line)) for line in para_lines)
            out_blocks.append(
                f'<p style="margin:0 0 14px 0; color:#1f2937; '
                f'line-height:1.55;">{joined}</p>'
            )
            para_lines = []

    for raw_line in body.split("\n"):
        line = raw_line.rstrip()
        if not line:
            flush_para()
            flush_list()
            continue
        if line.lstrip().startswith(("- ", "* ", "• ")):
            flush_para()
            in_list = True
            list_items.append(line.lstrip()[2:].strip())
        else:
            if in_list:
                flush_list()
            para_lines.append(line)

    flush_para()
    flush_list()
    return "\n".join(out_blocks)


def _render_signature_html(settings: Settings) -> str:
    name = escape(settings.comms_signature_name)
    team = escape(settings.comms_signature_team)
    company = escape(settings.comms_signature_company)
    return (
        '<div style="border-top:1px solid #e5e7eb; padding-top:14px; '
        'margin-top:6px; color:#374151; font-size:14px; line-height:1.5;">'
        '<div style="color:#6b7280; font-size:13px;">Best regards,</div>'
        f'<div style="font-weight:600; margin-top:8px;">{name}</div>'
        f'<div style="color:#4b5563;">{team}</div>'
        f'<div style="color:#4b5563;">{company}</div>'
        "</div>"
    )


def _render_signature_text(settings: Settings) -> str:
    return (
        "\n\nBest regards,\n"
        f"{settings.comms_signature_name}\n"
        f"{settings.comms_signature_team}\n"
        f"{settings.comms_signature_company}\n"
    )


def _render_footer_html(settings: Settings) -> str:
    parts: list[str] = []
    if settings.comms_disclose_ai_assistance:
        parts.append(
            "Prepared by AP Exception Agent and reviewed by the AP team "
            "before sending."
        )
    if settings.comms_signature_disclaimer:
        parts.append(escape(settings.comms_signature_disclaimer))
    if not parts:
        return ""
    return (
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="background:#f9fafb; border-top:1px solid #e5e7eb;">'
        '<tr><td style="padding:14px 24px; color:#6b7280; '
        'font-size:11px; line-height:1.5;">'
        + "<br/>".join(parts)
        + "</td></tr></table>"
    )


def render_html(draft: CommunicationDraft, settings: Settings) -> str:
    """Render the full HTML email body for a draft."""
    label, color = _CHANNEL_PRESETS.get(
        draft.channel, ("Notice", "#374151")
    )
    # Per-org brand color overrides the channel preset bar (if a hex was set).
    brand = (settings.comms_brand_color or "").strip()
    if brand.startswith("#"):
        color = brand
    body_html = _paragraphs_to_html(draft.body)
    sig_html = _render_signature_html(settings)
    footer_html = _render_footer_html(settings)
    subject = escape(draft.subject or f"AP exception {draft.invoice_id}")
    # Optional brand logo in the header bar (escaped; bounded height).
    logo_url = (settings.comms_logo_url or "").strip()
    logo_html = ""
    if logo_url.startswith(("http://", "https://")):
        logo_html = (
            f'<img src="{escape(logo_url)}" alt="{escape(settings.comms_signature_company)}" '
            'height="24" style="height:24px; margin-right:10px; vertical-align:middle;"/>'
        )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/><title>{subject}</title></head>
<body style="margin:0; padding:0; font-family: -apple-system, Segoe UI, Arial, Helvetica, sans-serif; background:#f4f6f8;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f4f6f8; padding:24px 0;">
<tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff; border-radius:8px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,0.08); max-width:640px;">
  <tr><td style="background:{color}; color:#ffffff; padding:14px 24px; font-size:13px; letter-spacing:0.6px; text-transform:uppercase; font-weight:600;">
    {logo_html}{label}
  </td></tr>
  <tr><td style="padding:24px; font-size:14px; color:#1f2937;">
    {body_html}
  </td></tr>
  <tr><td style="padding:0 24px 22px 24px;">
    {sig_html}
  </td></tr>
  <tr><td>
    {footer_html}
  </td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""


def render_text(draft: CommunicationDraft, settings: Settings) -> str:
    """Render the plain-text version — same content + signature, no chrome."""
    body = (draft.body or "").rstrip()
    out = body + _render_signature_text(settings)
    if settings.comms_signature_disclaimer:
        out += "\n--\n" + settings.comms_signature_disclaimer + "\n"
    return out


def _amount_str(amount: float | None) -> str:
    return f"${amount:,.2f}" if amount is not None else "n/a"


def render_consolidated(
    *, channel: CommChannel, items: list[dict], settings: Settings,
    attachment_note: str | None = None,
) -> tuple[str, str]:
    """Render ONE email consolidating several invoices going to the same recipient.

    Returns (text, html). ``items`` is a list of dicts with keys: invoice_id,
    vendor_name, amount (float|None), issue (str), subject (str|None), body (str).

    Default (``attachment_note`` is None): a short intro + a summary table + a
    per-invoice section — good for a handful of invoices. When ``attachment_note``
    is given (large batches sent with a spreadsheet attached), render a COMPACT
    body instead — intro + total + the attachment note, with no per-invoice
    sections or long table — so the email stays readable and the detail lives in
    the attachment."""
    n = len(items)
    total = sum(float(it["amount"]) for it in items if it.get("amount") is not None)
    compact = attachment_note is not None

    label, color = _CHANNEL_PRESETS.get(channel, ("Notice", "#374151"))
    brand = (settings.comms_brand_color or "").strip()
    if brand.startswith("#"):
        color = brand

    # ---- compact (attachment) body ----
    if compact:
        text = (
            f"The following {n} invoice(s) need your attention "
            f"(total {_amount_str(total)}).\n\n{attachment_note}\n"
        )
        text += _render_signature_text(settings)
        if settings.comms_signature_disclaimer:
            text += "\n--\n" + settings.comms_signature_disclaimer + "\n"

        inner = (
            f'<p style="margin:0 0 14px 0; color:#1f2937; line-height:1.55;">'
            f"The following <strong>{n}</strong> invoice(s) need your attention "
            f"(total <strong>{escape(_amount_str(total))}</strong>).</p>"
            f'<p style="margin:0 0 14px 0; color:#1f2937; line-height:1.55;">'
            f"{escape(attachment_note)}</p>"
        )
        html = _wrap_consolidated_html(inner=inner, settings=settings, label=label, color=color, n=n)
        return text, html

    # ---- plain text ----
    text_lines = [f"The following {n} invoice(s) need your attention:", ""]
    for it in items:
        text_lines.append(
            f"  - {it['invoice_id']}  {_amount_str(it.get('amount'))}  {it.get('issue') or ''}".rstrip()
        )
    for it in items:
        text_lines += [
            "",
            f"--- {it['invoice_id']} — {it.get('subject') or ''}".rstrip(),
            (it.get("body") or "").rstrip(),
        ]
    text = "\n".join(text_lines) + _render_signature_text(settings)
    if settings.comms_signature_disclaimer:
        text += "\n--\n" + settings.comms_signature_disclaimer + "\n"

    # ---- HTML ----
    rows_html = "".join(
        "<tr>"
        f'<td style="padding:6px 10px; border-bottom:1px solid #eee; font-family:monospace;">{escape(it["invoice_id"])}</td>'
        f'<td style="padding:6px 10px; border-bottom:1px solid #eee; text-align:right;">{escape(_amount_str(it.get("amount")))}</td>'
        f'<td style="padding:6px 10px; border-bottom:1px solid #eee;">{escape(it.get("issue") or "")}</td>'
        "</tr>"
        for it in items
    )
    summary = (
        '<table width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="border-collapse:collapse; font-size:13px; color:#1f2937; margin:0 0 18px 0;">'
        '<tr style="background:#f3f4f6;">'
        '<th align="left" style="padding:6px 10px;">Invoice</th>'
        '<th align="right" style="padding:6px 10px;">Amount</th>'
        '<th align="left" style="padding:6px 10px;">Issue</th></tr>'
        f"{rows_html}</table>"
    )
    sections = "".join(
        '<div style="margin:0 0 18px 0;">'
        '<div style="font-weight:600; color:#111827; border-bottom:1px solid #e5e7eb; '
        'padding-bottom:4px; margin-bottom:8px;">'
        f'{escape(it["invoice_id"])} — {escape(it.get("subject") or it["invoice_id"])}</div>'
        f'{_paragraphs_to_html(it.get("body") or "")}</div>'
        for it in items
    )
    intro = (
        f'<p style="margin:0 0 14px 0; color:#1f2937; line-height:1.55;">'
        f"The following <strong>{n}</strong> invoice(s) need your attention:</p>"
    )
    inner = intro + summary + sections
    html = _wrap_consolidated_html(inner=inner, settings=settings, label=label, color=color, n=n)
    return text, html


def _wrap_consolidated_html(
    *, inner: str, settings: Settings, label: str, color: str, n: int
) -> str:
    """Wrap the inner body in the branded consolidated-email shell (header, logo,
    signature, footer). Shared by the full and compact (attachment) renders."""
    sig_html = _render_signature_html(settings)
    footer_html = _render_footer_html(settings)
    logo_url = (settings.comms_logo_url or "").strip()
    logo_html = ""
    if logo_url.startswith(("http://", "https://")):
        logo_html = (
            f'<img src="{escape(logo_url)}" alt="{escape(settings.comms_signature_company)}" '
            'height="24" style="height:24px; margin-right:10px; vertical-align:middle;"/>'
        )

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/><title>{n} invoices</title></head>
<body style="margin:0; padding:0; font-family: -apple-system, Segoe UI, Arial, Helvetica, sans-serif; background:#f4f6f8;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f4f6f8; padding:24px 0;">
<tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0" border="0" style="background:#ffffff; border-radius:8px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,0.08); max-width:640px;">
  <tr><td style="background:{color}; color:#ffffff; padding:14px 24px; font-size:13px; letter-spacing:0.6px; text-transform:uppercase; font-weight:600;">
    {logo_html}{label}
  </td></tr>
  <tr><td style="padding:24px; font-size:14px; color:#1f2937;">
    {inner}
  </td></tr>
  <tr><td style="padding:0 24px 22px 24px;">
    {sig_html}
  </td></tr>
  <tr><td>
    {footer_html}
  </td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""
