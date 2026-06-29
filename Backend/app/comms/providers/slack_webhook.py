"""Slack Incoming Webhook provider.

Setup:
  1. https://api.slack.com/apps → Create New App → From scratch → name it
     "AP Exception Agent".
  2. In the app config, enable "Incoming Webhooks" and add one for the
     channel you want (e.g. #ap-escalations).
  3. Copy the webhook URL (https://hooks.slack.com/services/T.../B.../...).
  4. Set SLACK_WEBHOOK_URL in .env.

Each webhook is bound to one channel. To route to multiple channels by
exception type or resolution path, either create more webhooks (and key
them in code) or switch to a Slack Bot Token + chat.postMessage.
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Any

import httpx

from app.schemas import CommunicationDraft, resolution_path_label

log = logging.getLogger("ap_agent.comms.slack")


class SlackSendError(RuntimeError):
    """Raised when the webhook refuses or returns non-200."""


_SEVERITY_EMOJI = {
    "HIGH": ":rotating_light:",
    "MEDIUM": ":warning:",
    "LOW": ":information_source:",
}

_GREETING_RE = re.compile(r"^\s*(dear|hello|hi|hey)\b.*[,:]\s*$", re.IGNORECASE)
_SIGNOFF_RE = re.compile(
    r"^\s*(thank you|thanks|regards|best regards|best|sincerely|cheers)\b.*$",
    re.IGNORECASE,
)


def _fmt_amount(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return str(value)


def _to_mrkdwn(text: str) -> str:
    """Convert the email/markdown body into Slack mrkdwn and trim email cruft.

    - drop a leading greeting line ("Dear Finance Controller,") and trailing
      sign-off lines ("Thank you," / "Regards," ...) — the Block Kit header and
      fields already carry that context, so they're redundant noise in Slack
    - markdown bold ``**x**`` → Slack bold ``*x*``
    - markdown bullets ``- `` / ``* `` → ``• ``
    - collapse runs of blank lines
    """
    if not text:
        return ""
    lines = text.strip().split("\n")
    if lines and _GREETING_RE.match(lines[0]):
        lines = lines[1:]

    # Strip trailing sign-off block: blank lines, "Thank you,"/"Regards," lines,
    # and a short bare name/title line ("AP Operations Team") — in any order.
    def _is_signoff(line: str) -> bool:
        s = line.strip()
        if not s:
            return True
        if _SIGNOFF_RE.match(s):
            return True
        return len(s.split()) <= 4 and s.endswith(
            ("Team", "Operations", "Agent", "Department", "Controller")
        )

    while lines and _is_signoff(lines[-1]):
        lines.pop()

    body = "\n".join(lines).strip()
    body = re.sub(r"\*\*(.+?)\*\*", r"*\1*", body)          # **bold** -> *bold*
    body = re.sub(r"(?m)^\s*[-*]\s+", "• ", body)            # bullets -> •
    body = re.sub(r"\n{3,}", "\n\n", body)                   # collapse blanks
    return body


def _build_blocks(draft: CommunicationDraft, context: dict[str, Any] | None = None) -> list[dict]:
    """Build a structured Block Kit message.

    https://api.slack.com/block-kit
    """
    ctx = context or {}
    sev = str(ctx.get("severity") or "").upper()
    header = (draft.subject or f"AP exception {draft.invoice_id}").strip()
    emoji = _SEVERITY_EMOJI.get(sev, ":memo:")

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{emoji} {header}"[:150], "emoji": True},
        }
    ]

    # Scannable two-column field grid (Slack renders up to 10 fields).
    fields: list[dict] = [{"type": "mrkdwn", "text": f"*Invoice:*\n`{draft.invoice_id}`"}]

    def add(label: str, value: Any) -> None:
        if value not in (None, "", 0):
            fields.append({"type": "mrkdwn", "text": f"*{label}:*\n{value}"})

    add("Vendor", ctx.get("vendor_name"))
    add("Amount", _fmt_amount(ctx.get("invoice_amount")))
    add("Severity", sev.title() if sev else None)
    add("Exception", ctx.get("exception_type"))
    add("Recommended approach", resolution_path_label(ctx.get("resolution_path")))
    if ctx.get("sla_hours"):
        add("SLA", f"{ctx['sla_hours']}h")
    if ctx.get("days_outstanding"):
        add("Outstanding", f"{ctx['days_outstanding']}d")

    blocks.append({"type": "section", "fields": fields[:10]})
    blocks.append({"type": "divider"})

    body = _to_mrkdwn(draft.body)
    if body:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": body[:2900]}})

    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"Prepared by *AP Exception Agent* · "
                        f"template `{draft.template_id}` · model `{draft.model_id}`"
                    ),
                }
            ],
        }
    )
    return blocks


def send_via_slack_webhook(
    *,
    draft: CommunicationDraft,
    webhook_url: str,
    context: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Post the draft to Slack. Returns (local_message_id, slack_response)."""
    if not webhook_url:
        raise SlackSendError(
            "SLACK_WEBHOOK_URL is not configured — cannot send Slack messages."
        )

    msg_id = f"slack-{uuid.uuid4().hex[:12]}"
    payload = {
        # Plain-text fallback for clients/notifications that ignore blocks.
        "text": (draft.subject or draft.invoice_id) + "\n" + _to_mrkdwn(draft.body)[:500],
        "blocks": _build_blocks(draft, context),
    }
    try:
        resp = httpx.post(webhook_url, json=payload, timeout=15.0)
    except httpx.HTTPError as e:
        raise SlackSendError(f"network error: {e}") from e
    if resp.status_code >= 300:
        raise SlackSendError(
            f"webhook returned {resp.status_code}: {resp.text[:200]}"
        )
    log.info("slack: posted invoice=%s message_id=%s", draft.invoice_id, msg_id)
    return msg_id, resp.text
