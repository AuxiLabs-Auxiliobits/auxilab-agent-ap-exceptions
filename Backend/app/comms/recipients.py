"""Recipient resolver — vendor name → email / Slack channel.

This is the choke point that prevents the agent from sending to anywhere
the operator hasn't explicitly authorised.

Resolution order:
  1. Explicit override on the draft (caller passed `override_recipient`).
  2. Vendor master CSV at config.vendor_master_path (not yet shipped — stub).
  3. Channel-specific defaults:
       - Slack channels → the webhook is single-channel, no recipient needed
       - email channels → settings.comms_test_recipient (dev safety net)
  4. None → caller refuses to send and marks the draft SKIPPED.
"""
from __future__ import annotations

import csv
import logging
from functools import lru_cache
from pathlib import Path

from app.config import Settings
from app.schemas import CommChannel, CommunicationDraft

log = logging.getLogger("ap_agent.comms.recipients")


@lru_cache(maxsize=8)
def _load_vendor_master(path_str: str) -> dict[str, str]:
    """Parse a vendor master CSV into {normalized_vendor_name: email}.

    Expected columns (case-insensitive, flexible aliases):
      vendor_name | vendor | name      → the vendor name
      email | vendor_email | ar_email  → the AR contact address

    Cached by path string so we parse the file once per process. Missing or
    malformed files yield an empty map (the caller then falls back safely).
    """
    path = Path(path_str)
    if not path.is_file():
        log.warning("vendor master CSV not found at %s — using test-recipient fallback", path)
        return {}
    name_keys = ("vendor_name", "vendor", "name")
    email_keys = ("email", "vendor_email", "ar_email", "contact_email")
    mapping: dict[str, str] = {}
    try:
        with path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            norm = {(k or "").strip().lower(): k for k in (reader.fieldnames or [])}
            name_col = next((norm[k] for k in name_keys if k in norm), None)
            email_col = next((norm[k] for k in email_keys if k in norm), None)
            if not name_col or not email_col:
                log.error(
                    "vendor master CSV %s missing a name/email column "
                    "(have: %s) — falling back to test recipient",
                    path,
                    reader.fieldnames,
                )
                return {}
            for row in reader:
                name = (row.get(name_col) or "").strip().lower()
                email = (row.get(email_col) or "").strip()
                if name and "@" in email:
                    mapping[name] = email
    except Exception as e:  # noqa: BLE001 — never let a bad CSV crash a send
        log.error("failed to parse vendor master CSV %s: %s", path, e)
        return {}
    log.info("vendor master loaded: %d vendors from %s", len(mapping), path)
    return mapping


def _lookup_vendor_email(vendor_name: str | None, settings: Settings) -> str | None:
    """Resolve a vendor's AR email from the vendor master, if configured."""
    if not settings.vendor_master_path or not vendor_name:
        return None
    master = _load_vendor_master(str(settings.vendor_master_path))
    if not master:
        return None
    return master.get(vendor_name.strip().lower())


def resolve_recipient(
    *,
    draft: CommunicationDraft,
    settings: Settings,
    override: str | None = None,
    vendor_name: str | None = None,
    tenant_id: str | None = None,
) -> str | None:
    """Return the resolved recipient, or None to refuse the send.

    For VENDOR_EMAIL the precedence is: explicit override → the tenant's vendor
    directory (managed vendor→email) → legacy VENDOR_MASTER_PATH CSV → dev test
    recipient. ``tenant_id`` scopes the directory lookup."""
    if override:
        return override.strip() or None

    if draft.channel == CommChannel.FINANCE_NOTE:
        # Finance Controller escalations: prefer the dedicated controller
        # mailbox, then the AP team mailbox, then the test recipient. The
        # webhook (if configured) goes via Slack instead — the dispatcher
        # decides; the resolver just returns the email destination so the
        # Slack-not-configured fallback path has somewhere to send.
        return (
            settings.comms_finance_controller_mailbox
            or settings.comms_ap_team_mailbox
            or settings.comms_test_recipient
            or None
        )

    if draft.channel == CommChannel.SLACK:
        # When the webhook is configured the dispatcher posts there directly;
        # this email destination is the fallback for when SLACK_WEBHOOK_URL
        # is empty AND for audit visibility.
        return (
            settings.comms_ap_team_mailbox
            or settings.comms_test_recipient
            or None
        )

    # Vendor master lookup (VENDOR_EMAIL): resolve the real AR contact by
    # vendor name when VENDOR_MASTER_PATH is configured. INTERNAL_EMAIL stays
    # internal — it goes to the AP team / test recipient, never to a vendor.
    if draft.channel == CommChannel.VENDOR_EMAIL:
        # Managed per-tenant vendor directory takes precedence over the legacy CSV.
        from app.api import vendor_directory

        dir_email = vendor_directory.get_email(tenant_id, vendor_name)
        if dir_email:
            return dir_email
        vendor_email = _lookup_vendor_email(vendor_name, settings)
        if vendor_email:
            return vendor_email
        if settings.vendor_master_path:
            # Master is configured but this vendor isn't in it — do NOT silently
            # fall back to the test recipient in that case; refuse so the gap is
            # visible rather than mis-delivering. Without a master, the dev
            # test-recipient safety net below still applies.
            log.warning(
                "vendor master configured but no email for vendor=%r (invoice=%s) — refusing send",
                vendor_name,
                draft.invoice_id,
            )
            return None

    # Dev fallback for vendor_email / internal_email: send everything to the
    # test recipient until vendor master lookups exist. This is the safety
    # pattern that prevents accidentally hammering real vendor inboxes.
    return (
        settings.comms_test_recipient
        or settings.comms_ap_team_mailbox
        or None
    )
