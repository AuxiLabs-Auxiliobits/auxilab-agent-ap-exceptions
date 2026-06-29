"""Communication draft schemas."""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class CommChannel(str, Enum):
    VENDOR_EMAIL = "vendor_email"
    INTERNAL_EMAIL = "internal_email"
    SLACK = "slack"
    FINANCE_NOTE = "finance_note"


class SendStatus(str, Enum):
    DRAFT = "draft"           # never attempted
    SENDING = "sending"       # claimed by a send in flight (concurrency guard)
    DRYRUN = "dryrun"         # written to artifacts/sent/ but no real provider hit
    SENT = "sent"             # real provider accepted it
    FAILED = "failed"         # real provider rejected it
    SKIPPED = "skipped"       # blocked by safety guard (no recipient, etc.)


# States from which a (re)send may be atomically claimed → SENDING. Excludes
# SENT/DRYRUN (terminal, idempotent) and SENDING itself (already in flight).
CLAIMABLE_SEND_STATES: frozenset[SendStatus] = frozenset(
    {SendStatus.DRAFT, SendStatus.FAILED, SendStatus.SKIPPED}
)


def claimable_for_send(
    send_status: "SendStatus",
    send_claimed_at: "datetime | None",
    now: "datetime",
    ttl_seconds: float,
    *,
    force: bool = False,
) -> bool:
    """Whether a draft may be (re)claimed for sending.

    Claimable from a non-terminal state, OR from a STALE in-flight claim — a
    SENDING draft whose claim timestamp is older than ``ttl_seconds``. The stale
    case makes the concurrency guard self-healing: a worker killed mid-send
    leaves a draft in SENDING, and without this it would be wedged forever. A
    live, recent SENDING claim is NOT claimable, so genuinely concurrent sends
    still can't double-fire. A SENDING draft with no claim timestamp is treated
    as in-flight (not reclaimable) — every real claim stamps the timestamp, so a
    missing one is never a stale claim to recover.

    ``force=True`` is an EXPLICIT operator resend: it additionally allows
    reclaiming a terminal SENT/DRYRUN draft (e.g. to re-send to a corrected
    vendor email). It does NOT bypass a live in-flight SENDING claim — that
    still protects against two concurrent resend clicks racing into a
    double-send."""
    if send_status in CLAIMABLE_SEND_STATES:
        return True
    if force and send_status in (SendStatus.SENT, SendStatus.DRYRUN):
        return True
    if send_status is SendStatus.SENDING and send_claimed_at is not None:
        return (now - send_claimed_at).total_seconds() >= ttl_seconds
    return False


class CommunicationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_id: str
    channel: CommChannel
    recipient_hint: str
    subject: str | None = None
    body: str = Field(min_length=1, max_length=4000)
    tone: str = "professional"
    template_id: str
    model_id: str
    is_edited_by_human: bool = False

    # ---- send lifecycle (populated by the comms dispatcher) ----
    recipient: str | None = None                 # resolved email / slack channel
    send_status: SendStatus = SendStatus.DRAFT
    send_provider: str | None = None             # "gmail_smtp", "slack_webhook", "dryrun"
    send_message_id: str | None = None           # provider's id or our local id
    sent_at: datetime | None = None
    send_claimed_at: datetime | None = None       # when SENDING was claimed (lease/TTL)
    send_error: str | None = None                # human-readable error if FAILED
