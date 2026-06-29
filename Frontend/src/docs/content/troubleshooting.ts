import { h1, h2, p, type Block } from '../blocks';

const blocks: Block[] = [
  h1('Troubleshooting'),
  p('Symptom → cause → fix for the most common issues. If you are stuck, capture the `run_id` and the time, and contact your administrator.'),

  h2('Upload failures'),
  p('**"File too large" (`413`)** — the file exceeds 25 MB. Split the queue or remove unused columns, then re-upload.'),
  p('**"Empty file" / "filename required" (`400`)** — the file is zero bytes or has no name. Re-export from your ERP and retry.'),
  p('**The upload spins and never finishes** — check `GET /readyz`. A `503` means the run store or database is unreachable; the run cannot persist. Once the dependency is healthy, re-upload.'),
  p('**Nothing happens after I drop a file** — confirm you are signed in (an expired session shows a "session expired" message). Sign in again and retry.'),

  h2('Missing or unmapped columns'),
  p('**"Missing required column: …"** — a required header could not be matched, even by alias. Compare your headers to [File Import](/docs/file-import); rename the column or add the canonical header.'),
  p('**A column I expected was ignored** — it did not match a known alias. Use the canonical name, or ask your administrator to add the alias.'),

  h2('Invalid data / quarantined rows'),
  p('**Rows show up in Quarantined** — open **Queue → Quarantined** to see the reason code per row (`INVALID_AMOUNT`, `INVALID_DAYS`, `MISSING_FIELD`, `FUTURE_DATE`). Download the **rejection report**, fix those rows, and re-upload just them.'),
  p('**`INVALID_AMOUNT`** — the amount did not parse to a number ≥ 0. Remove text, fix negatives, ensure a decimal point (not a comma) for cents.'),
  p('**`FUTURE_DATE`** — an invoice/exception date is in the future. Correct the date.'),

  h2('Duplicate detection issues'),
  p('**A real duplicate was not caught** — duplicate signals come from the description. Make sure your ERP export notes the matching invoice number/amount in `exception_description`, or pre-tag `exception_type = Duplicate`.'),
  p('**A legitimate invoice was held as a duplicate** — open it in **Resolution**, read the rationale, and clear it manually. Suspected duplicates are **held, never auto-paid** — by design.'),

  h2('Slack notification failures'),
  p('**Slack messages are not arriving** — confirm `SLACK_WEBHOOK_URL` is set and points at the right channel. If it is unset, finance-note/Slack drafts **fall back to email** (with a subject prefix) — check the finance-controller/AP mailbox.'),
  p('**A send is `skipped`** — no recipient could be resolved (no vendor master and no test recipient), or the recipient domain is not on the live-send allow-list. Configure `VENDOR_MASTER_PATH` / `COMMS_ALLOWED_DOMAINS` (see [Administrator Guide](/docs/admin-guide)).'),
  p('**A send is `failed`** — the provider rejected it (bad SMTP credentials, invalid webhook). Check the `error_message` on the send result and the server logs.'),

  h2('Dashboard mismatches'),
  p('**Counts do not add up** — `accepted + quarantined` should equal rows submitted. If they do not, some rows failed to parse at the file level — check the rejection report.'),
  p('**"Run not found on the backend"** — the active run pointer is stale (a previous session, or the in-memory store was cleared on a restart). The console now clears this automatically and returns you to the upload state; just upload again. For durability, use a durable run store (see [Administrator Guide](/docs/admin-guide)).'),
  p('**Metrics look empty** — the run may still be processing (`PENDING`/`RUNNING`) or ended in `FAILED`. Check `GET /v1/runs/{id}`.'),

  h2('Performance issues'),
  p('**Large queues are slow** — classification runs with bounded concurrency. For big files, enable the **durable run queue** and increase `RUN_QUEUE_CONCURRENCY`, or run multiple instances.'),
  p('**AI calls time out** — a per-call timeout bounds a hung provider response; the row is recorded as an error and the run continues. Check provider status and your API key/quota. With no key, the platform runs in deterministic mock mode.'),
  p('**`429 Too Many Requests`** — you hit the API rate limit (default `240/minute`). Back off and poll less aggressively.'),
];

export default blocks;
