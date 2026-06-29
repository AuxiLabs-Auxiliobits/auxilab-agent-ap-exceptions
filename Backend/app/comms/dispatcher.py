"""Comms dispatcher — routes a CommunicationDraft to the right provider.

Responsibilities:
  - Resolve the recipient (or refuse the send).
  - Decide dry-run vs live based on settings.comms_dryrun.
  - Idempotency: a draft already in SENT / DRYRUN status returns its prior
    result instead of double-sending.
  - Always returns a SendResult; never raises into the caller (errors are
    captured in result.error_message + result.status=FAILED).
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.comms.email_template import render_consolidated
from app.comms.oauth import OAuthError, slack_post
from app.comms.providers.dryrun import send_dryrun, write_consolidated_preview
from app.comms.providers.gmail_oauth import (
    send_email_via_gmail_oauth,
    send_prebuilt_via_gmail_oauth,
)
from app.comms.providers.gmail_smtp import (
    GmailSendError,
    send_email_via_gmail,
    send_simple_email,
)
from app.comms.providers.slack_webhook import (
    SlackSendError,
    _build_blocks,
    _to_mrkdwn,
    send_via_slack_webhook,
)
from app.comms.recipients import resolve_recipient
from app.config import Settings, get_settings
from app.schemas import CommChannel, CommunicationDraft, SendStatus

log = logging.getLogger("ap_agent.comms.dispatch")


class _InProcessDailyCap:
    """In-process per-(tenant, domain) daily live-send counter.

    Guards against runaway escalation storms: at most ``cap`` live emails per
    (tenant, recipient domain) per UTC day. ``reserve()`` atomically counts a
    slot if under cap; ``release()`` returns it when a send fails. Process-local
    (resets on restart, NOT shared across replicas) — correct only for a single
    instance; multi-replica deployments use the DB-backed cap (engaged when
    ``DB_PERSISTENCE_ENABLED``). ``cap <= 0`` means unlimited."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[tuple[str, str, str], int] = {}  # (tenant_id, day_iso, domain)

    def reserve(self, *, tenant_id: str, domain: str, day_iso: str, cap: int) -> bool:
        if cap <= 0:
            return True  # unlimited — don't bother counting
        key = (tenant_id, day_iso, domain)
        with self._lock:
            if len(self._counts) > 4096:  # bound memory: drop stale days
                self._counts = {k: v for k, v in self._counts.items() if k[1] == day_iso}
            if self._counts.get(key, 0) >= cap:
                return False
            self._counts[key] = self._counts.get(key, 0) + 1
            return True

    def release(self, *, tenant_id: str, domain: str, day_iso: str) -> None:
        key = (tenant_id, day_iso, domain)
        with self._lock:
            if self._counts.get(key, 0) > 0:
                self._counts[key] -= 1


class _DbDailyCap:
    """Distributed per-(tenant, domain) daily send cap backed by a DB row.

    ``reserve()`` is an atomic conditional increment (INSERT ... ON CONFLICT DO
    UPDATE ... WHERE count < cap RETURNING), so the cap holds across replicas
    rather than per-process. ``release()`` decrements on a failed send. Works on
    SQLite (≥3.35) and PostgreSQL. ``cap <= 0`` means unlimited."""

    _ensured_engine_id: int | None = None

    def _ensure_table(self) -> None:
        from app.db.session import get_engine

        eng = get_engine()
        if _DbDailyCap._ensured_engine_id == id(eng):
            return
        from app.db.models import CommsSendCounter

        CommsSendCounter.__table__.create(bind=eng, checkfirst=True)
        _DbDailyCap._ensured_engine_id = id(eng)

    def reserve(self, *, tenant_id: str, domain: str, day_iso: str, cap: int) -> bool:
        if cap <= 0:
            return True
        from sqlalchemy import text

        from app.db.session import session_scope

        self._ensure_table()
        sql = text(
            "INSERT INTO comms_send_counters (tenant_id, day_iso, domain, count) "
            "VALUES (:t, :d, :dom, 1) "
            "ON CONFLICT (tenant_id, day_iso, domain) "
            "DO UPDATE SET count = comms_send_counters.count + 1 "
            "WHERE comms_send_counters.count < :cap "
            "RETURNING count"
        )
        with session_scope() as s:
            row = s.execute(
                sql, {"t": tenant_id, "d": day_iso, "dom": domain, "cap": cap}
            ).fetchone()
        return row is not None

    def release(self, *, tenant_id: str, domain: str, day_iso: str) -> None:
        from sqlalchemy import text

        from app.db.session import session_scope

        self._ensure_table()
        sql = text(
            "UPDATE comms_send_counters SET count = count - 1 "
            "WHERE tenant_id = :t AND day_iso = :d AND domain = :dom AND count > 0"
        )
        with session_scope() as s:
            s.execute(sql, {"t": tenant_id, "d": day_iso, "dom": domain})


_DOMAIN_CAP = _InProcessDailyCap()
_DB_CAP = _DbDailyCap()


def _cap_for(settings: Settings):
    """DB-backed cap when persistence is on (holds across replicas); else in-process."""
    return _DB_CAP if settings.db_persistence_enabled else _DOMAIN_CAP


def reset_domain_cap() -> None:
    """Test helper — clear the in-process daily send counters."""
    global _DOMAIN_CAP
    _DOMAIN_CAP = _InProcessDailyCap()


@dataclass
class SendResult:
    invoice_id: str
    status: SendStatus
    provider: str
    message_id: str | None
    recipient: str | None
    sent_at: datetime | None
    error_message: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def dispatch(
    *,
    draft: CommunicationDraft,
    run_id: str,
    settings: Settings | None = None,
    recipient_override: str | None = None,
    context: dict[str, Any] | None = None,
    tenant_id: str | None = None,
    force: bool = False,
) -> SendResult:
    """Route a draft to its provider and record the outcome as a metric.

    ``context`` is optional structured metadata (vendor, amount, severity,
    exception_type, resolution_path, sla_hours, days_outstanding) used to render
    the Slack Block Kit fields and to resolve the vendor master recipient.
    ``tenant_id`` scopes the per-domain daily send cap so one org can't consume
    another's quota. ``force=True`` is an explicit operator resend: it skips the
    "already sent" idempotency short-circuit so the recipient is re-resolved from
    the current vendor directory (picks up an edited vendor email).
    """
    result = _dispatch_impl(
        draft=draft,
        run_id=run_id,
        settings=settings,
        recipient_override=recipient_override,
        context=context,
        tenant_id=tenant_id,
        force=force,
    )
    try:
        from app.observability import record_comms_send

        record_comms_send(status=result.status.value, provider=result.provider)
    except Exception:  # noqa: BLE001 — metrics must never break a send
        log.debug("metrics: record_comms_send failed", exc_info=True)
    return result


def _dispatch_impl(
    *,
    draft: CommunicationDraft,
    run_id: str,
    settings: Settings | None = None,
    recipient_override: str | None = None,
    context: dict[str, Any] | None = None,
    tenant_id: str | None = None,
    force: bool = False,
) -> SendResult:
    s = settings or get_settings()
    tenant_key = tenant_id or ""  # cap bucket; "" = the single-tenant/default bucket

    # 1. Idempotency — if we already sent this draft, return the prior result
    #    without retrying. The caller is expected to display the recorded
    #    send_status / send_message_id from the draft itself. An explicit resend
    #    (force=True) skips this so the recipient is re-resolved fresh below.
    if not force and draft.send_status in (SendStatus.SENT, SendStatus.DRYRUN):
        log.info(
            "dispatch: idempotent — invoice=%s already in status=%s",
            draft.invoice_id,
            draft.send_status.value,
        )
        return SendResult(
            invoice_id=draft.invoice_id,
            status=draft.send_status,
            provider=draft.send_provider or "unknown",
            message_id=draft.send_message_id,
            recipient=draft.recipient,
            sent_at=draft.sent_at,
        )

    # 2. Resolve recipient (or refuse). The vendor name (carried in `context`)
    #    lets the resolver hit the vendor master for VENDOR_EMAIL drafts.
    ctx = context or {}
    vendor_name = ctx.get("vendor_name") or ctx.get("vendor")
    recipient = resolve_recipient(
        draft=draft, settings=s, override=recipient_override, vendor_name=vendor_name,
        tenant_id=tenant_id,
    )
    if recipient is None:
        log.warning(
            "dispatch: SKIPPED — no recipient resolved for invoice=%s channel=%s",
            draft.invoice_id,
            draft.channel.value,
        )
        return SendResult(
            invoice_id=draft.invoice_id,
            status=SendStatus.SKIPPED,
            provider="none",
            message_id=None,
            recipient=None,
            sent_at=None,
            error_message="No recipient resolved — set vendor master or test recipient.",
        )

    # 3. Dry-run path
    if s.comms_dryrun:
        msg_id, path = send_dryrun(
            draft=draft,
            recipient=recipient,
            run_id=run_id,
            sent_dir=s.comms_sent_dir,
            sender=s.gmail_smtp_user or "ap-agent@local",
            bcc=s.comms_ap_team_mailbox if s.comms_ap_team_mailbox != recipient else None,
            settings=s,
        )
        return SendResult(
            invoice_id=draft.invoice_id,
            status=SendStatus.DRYRUN,
            provider="dryrun",
            message_id=msg_id,
            recipient=recipient,
            sent_at=_now(),
        )

    # 3b. Live-send safety allowlist. When COMMS_ALLOWED_DOMAINS is set, a real
    # (non-dry-run) send is only permitted to those recipient domains — so a bad
    # run can never email arbitrary vendor domains. Slack webhooks (no "@") are
    # exempt. Empty allowlist => allow all (back-compat).
    allowed = s.comms_allowed_domains_list
    if allowed and "@" in recipient:
        domain = recipient.rsplit("@", 1)[-1].lower()
        if domain not in allowed:
            log.warning(
                "dispatch: BLOCKED — recipient domain %r not in COMMS_ALLOWED_DOMAINS (invoice=%s)",
                domain,
                draft.invoice_id,
            )
            return SendResult(
                invoice_id=draft.invoice_id,
                status=SendStatus.SKIPPED,
                provider="none",
                message_id=None,
                recipient=recipient,
                sent_at=None,
                error_message=f"Recipient domain '{domain}' not in allowlist — live send blocked.",
            )

    # 3c. Per-domain daily cap — reserve a slot atomically (releasing it if the
    # send fails). Block live email once a recipient domain has hit
    # COMMS_PER_DOMAIN_DAILY_CAP sends today (escalation-storm guard). The cap is
    # DB-backed (cross-replica) when persistence is on, else in-process.
    send_domain = recipient.rsplit("@", 1)[-1].lower() if "@" in recipient else None
    day_iso = _now().date().isoformat()
    cap = _cap_for(s)
    if send_domain and not cap.reserve(
        tenant_id=tenant_key, domain=send_domain, day_iso=day_iso, cap=s.comms_per_domain_daily_cap
    ):
        log.warning(
            "dispatch: CAPPED — domain %r hit daily cap %d (invoice=%s)",
            send_domain,
            s.comms_per_domain_daily_cap,
            draft.invoice_id,
        )
        return SendResult(
            invoice_id=draft.invoice_id,
            status=SendStatus.SKIPPED,
            provider="none",
            message_id=None,
            recipient=recipient,
            sent_at=None,
            error_message=(
                f"Daily send cap ({s.comms_per_domain_daily_cap}) reached for "
                f"domain '{send_domain}' — send skipped."
            ),
        )

    # 4. Live send — route by channel
    try:
        if draft.channel in (CommChannel.VENDOR_EMAIL, CommChannel.INTERNAL_EMAIL):
            bcc = (
                s.comms_ap_team_mailbox
                if s.comms_ap_team_mailbox
                and s.comms_ap_team_mailbox.lower() != recipient.lower()
                else None
            )
            # Prefer the org's OAuth Gmail connection over an SMTP app password.
            if s.gmail_oauth_refresh_token:
                msg_id, _resp = send_email_via_gmail_oauth(
                    draft=draft, recipient=recipient, settings=s, bcc=bcc
                )
                provider = "gmail_oauth"
            else:
                msg_id, _resp = send_email_via_gmail(
                    draft=draft, recipient=recipient, settings=s, bcc=bcc
                )
                provider = "gmail_smtp"

        elif draft.channel in (CommChannel.SLACK, CommChannel.FINANCE_NOTE):
            if s.slack_bot_token:
                # Preferred: Slack app (OAuth) via chat.postMessage.
                channel = s.slack_channel or s.slack_default_channel
                text = (draft.subject or draft.invoice_id) + "\n" + _to_mrkdwn(draft.body)[:500]
                ts = slack_post(s.slack_bot_token, channel, text, _build_blocks(draft, context))
                msg_id = f"slack-{ts}"
                provider = "slack_bot"
            elif s.slack_webhook_url:
                # Legacy: incoming webhook.
                msg_id, _resp = send_via_slack_webhook(
                    draft=draft, webhook_url=s.slack_webhook_url, context=context
                )
                provider = "slack_webhook"
            else:
                # Graceful degradation: Slack not configured → send via email
                # to the Finance Controller (or AP team) mailbox. The subject
                # is prefixed so the recipient knows the agent would have
                # posted this to #ap-escalations if Slack were wired up.
                prefix = (
                    "[Finance escalation] "
                    if draft.channel == CommChannel.FINANCE_NOTE
                    else "[Internal escalation] "
                )
                # Strip redundant "Escalation:" / "Internal:" prefixes the
                # LLM may have added so the subject doesn't read "[Finance
                # escalation] Escalation: ..." (looks unprofessional).
                raw_subject = (
                    draft.subject or f"AP exception {draft.invoice_id}"
                ).strip()
                for redundant in (
                    "Escalation:",
                    "ESCALATION:",
                    "Internal escalation:",
                    "Internal:",
                    "Finance escalation:",
                ):
                    if raw_subject.lower().startswith(redundant.lower()):
                        raw_subject = raw_subject[len(redundant):].strip()
                adapted = draft.model_copy(
                    update={
                        "subject": prefix + raw_subject,
                    }
                )
                log.info(
                    "dispatch: SLACK_WEBHOOK_URL not set → falling back to "
                    "email for invoice=%s channel=%s recipient=%s",
                    draft.invoice_id,
                    draft.channel.value,
                    recipient,
                )
                bcc = (
                    s.comms_ap_team_mailbox
                    if s.comms_ap_team_mailbox
                    and s.comms_ap_team_mailbox.lower() != recipient.lower()
                    else None
                )
                msg_id, _resp = send_email_via_gmail(
                    draft=adapted, recipient=recipient, settings=s, bcc=bcc
                )
                provider = "gmail_smtp(slack_fallback)"

        else:
            if send_domain:
                cap.release(tenant_id=tenant_key, domain=send_domain, day_iso=day_iso)
            return SendResult(
                invoice_id=draft.invoice_id,
                status=SendStatus.FAILED,
                provider="none",
                message_id=None,
                recipient=recipient,
                sent_at=None,
                error_message=f"Unsupported channel: {draft.channel.value}",
            )

    except (GmailSendError, SlackSendError, OAuthError) as e:
        # Send failed — return the reserved cap slot so a failure doesn't burn quota.
        if send_domain:
            cap.release(tenant_id=tenant_key, domain=send_domain, day_iso=day_iso)
        log.exception(
            "dispatch: send FAILED invoice=%s channel=%s err=%s",
            draft.invoice_id,
            draft.channel.value,
            e,
        )
        return SendResult(
            invoice_id=draft.invoice_id,
            status=SendStatus.FAILED,
            provider="gmail" if isinstance(e, GmailSendError) else "slack",
            message_id=None,
            recipient=recipient,
            sent_at=None,
            error_message=str(e)[:500],
        )

    # Success — the reservation made in 3c stands as this send's quota count.
    return SendResult(
        invoice_id=draft.invoice_id,
        status=SendStatus.SENT,
        provider=provider,
        message_id=msg_id,
        recipient=recipient,
        sent_at=_now(),
    )


# Email channels whose multiple drafts to one recipient can be coalesced into a
# single consolidated email. (Slack/finance-note groups are sent per-draft.)
CONSOLIDATABLE_CHANNELS = (CommChannel.VENDOR_EMAIL, CommChannel.INTERNAL_EMAIL)


def dispatch_consolidated(
    *,
    recipient: str,
    channel: CommChannel,
    drafts: list[CommunicationDraft],
    rows_by_id: dict[str, Any],
    run_id: str,
    settings: Settings | None = None,
    tenant_id: str | None = None,
) -> SendResult:
    """Send ONE email to ``recipient`` covering every draft in ``drafts`` (all of
    which already resolved to this recipient on this channel) — instead of one
    email per invoice. Applies the same dry-run / allowlist / per-domain-cap
    gates as a normal send, reserving a SINGLE cap slot for the consolidated
    message. The caller is responsible for having claimed each draft and for
    recording the returned result onto each one. ``invoice_id`` on the result is
    a synthetic group id; statuses/message_id apply to the whole group."""
    s = settings or get_settings()
    tenant_key = tenant_id or ""
    group_id = f"bulk:{run_id}:{len(drafts)}"

    items = []
    for d in drafts:
        row = rows_by_id.get(d.invoice_id)
        items.append(
            {
                "invoice_id": d.invoice_id,
                "vendor_name": getattr(row, "vendor_name", None),
                "amount": float(row.invoice_amount) if row is not None else None,
                "issue": getattr(row, "exception_type", None) or d.template_id,
                "days_outstanding": getattr(row, "days_outstanding", None),
                "po_number": getattr(row, "po_number", None),
                "subject": d.subject,
                "body": d.body,
            }
        )
    vendor = items[0]["vendor_name"] if items else None
    n = len(items)
    subject = (
        f"{vendor}: {n} invoices need attention"
        if vendor
        else f"[AP] {n} invoices need attention"
    )

    # Past the threshold, attach the full list as a spreadsheet and keep the
    # email body short — inlining a section per invoice becomes an unreadable
    # wall of text for large batches.
    attachments = None
    attachment_note = None
    if n > s.comms_consolidated_attachment_threshold:
        from app.comms.attachments import build_invoice_attachment

        att = build_invoice_attachment(items, vendor=vendor, count=n)
        attachments = [att]
        attachment_note = f"Full details for all {n} invoices are attached: {att.filename}"

    text, html_full = render_consolidated(
        channel=channel, items=items, settings=s, attachment_note=attachment_note
    )
    html = html_full if s.comms_email_html_enabled else None
    invoice_ids = [d.invoice_id for d in drafts]
    bcc = (
        s.comms_ap_team_mailbox
        if s.comms_ap_team_mailbox and s.comms_ap_team_mailbox.lower() != recipient.lower()
        else None
    )

    def _result(status, provider, message_id, error=None) -> SendResult:
        try:
            from app.observability import record_comms_send

            record_comms_send(status=status.value, provider=provider)
        except Exception:  # noqa: BLE001 — metrics must never break a send
            log.debug("metrics: record_comms_send failed", exc_info=True)
        return SendResult(
            invoice_id=group_id, status=status, provider=provider,
            message_id=message_id, recipient=recipient, sent_at=_now() if message_id else None,
            error_message=error,
        )

    # Dry-run: write a consolidated preview, no provider hit.
    if s.comms_dryrun:
        msg_id, _path = write_consolidated_preview(
            subject=subject, text=text, html=html, recipient=recipient, bcc=bcc,
            run_id=run_id, sent_dir=s.comms_sent_dir,
            sender=s.gmail_smtp_user or "ap-agent@local", invoice_ids=invoice_ids,
            attachments=attachments,
        )
        return _result(SendStatus.DRYRUN, "dryrun", msg_id)

    # Allowlist (live sends only).
    allowed = s.comms_allowed_domains_list
    domain = recipient.rsplit("@", 1)[-1].lower() if "@" in recipient else None
    if allowed and domain and domain not in allowed:
        return _result(
            SendStatus.SKIPPED, "none", None,
            error=f"Recipient domain '{domain}' not in allowlist — live send blocked.",
        )

    # Per-domain daily cap — reserve ONE slot for the whole consolidated email.
    cap = _cap_for(s)
    day_iso = _now().date().isoformat()
    if domain and not cap.reserve(
        tenant_id=tenant_key, domain=domain, day_iso=day_iso, cap=s.comms_per_domain_daily_cap
    ):
        return _result(
            SendStatus.SKIPPED, "none", None,
            error=f"Daily send cap reached for domain '{domain}' — consolidated send skipped.",
        )

    try:
        reply_to = s.comms_ap_team_mailbox or None
        if s.gmail_oauth_refresh_token:
            msg_id, _ = send_prebuilt_via_gmail_oauth(
                to=recipient, subject=subject, text=text, html=html,
                settings=s, bcc=bcc, reply_to=reply_to, attachments=attachments,
            )
            provider = "gmail_oauth"
        else:
            msg_id, _ = send_simple_email(
                to=recipient, subject=subject, text=text, html=html,
                settings=s, reply_to=reply_to, bcc=bcc, attachments=attachments,
            )
            provider = "gmail_smtp"
    except GmailSendError as e:
        if domain:
            cap.release(tenant_id=tenant_key, domain=domain, day_iso=day_iso)
        log.exception("dispatch_consolidated: send FAILED recipient=%s err=%s", recipient, e)
        return _result(SendStatus.FAILED, "gmail", None, error=str(e)[:500])

    log.info("dispatch_consolidated: sent %d invoices to %s", n, recipient)
    return _result(SendStatus.SENT, provider, msg_id)
