"""Send a newsletter to all active subscribers (server-side CLI).

Run from the Backend dir with the same env as the app (so SMTP + DB resolve):

    python -m scripts.send_newsletter --subject "June update" --body-file body.txt
    python -m scripts.send_newsletter --subject "Hi" --body "Short note" --dry-run

Each email carries the subscriber's unsubscribe link. For large lists prefer a
real ESP — Gmail has daily caps and bulk-from-Gmail risks spam classification.
"""
from __future__ import annotations

import argparse
import sys

from app.api import subscribers
from app.comms import marketing_email
from app.comms.providers.gmail_smtp import send_bulk_emails
from app.config import get_settings


def main() -> int:
    ap = argparse.ArgumentParser(description="Send a newsletter to all active subscribers.")
    ap.add_argument("--subject", required=True)
    ap.add_argument("--body", help="Inline body text.")
    ap.add_argument("--body-file", help="Read the body from a file (UTF-8).")
    ap.add_argument("--dry-run", action="store_true", help="Count recipients, don't send.")
    args = ap.parse_args()

    if args.body:
        body = args.body
    elif args.body_file:
        with open(args.body_file, encoding="utf-8") as f:
            body = f.read()
    else:
        body = sys.stdin.read()

    s = get_settings()
    active = subscribers.list_active()
    print(f"{len(active)} active subscriber(s).")
    if args.dry_run:
        print("Dry run — nothing sent.")
        return 0
    if not active:
        return 0

    messages = []
    for sub in active:
        html, text = marketing_email.newsletter(
            args.subject, body, subscribers.unsubscribe_url(sub["unsubscribe_token"]), s
        )
        messages.append({"to": sub["email"], "subject": args.subject, "text": text, "html": html})
    results = send_bulk_emails(messages=messages, settings=s)
    sent = sum(1 for r in results if r["ok"])
    print(f"Sent {sent}/{len(results)} ({len(results) - sent} failed).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
