import { h1, h2, p, ol, table, warn, note, hr, type Block } from '../blocks';

const blocks: Block[] = [
  h1('Administrator Guide'),
  p('Everything an administrator configures to run the platform safely in production. Settings are environment-driven; the non-secret subset is readable in the console (**Settings**) and via `GET /v1/config`.'),
  warn('**Production safety gate:** in a `production`/`staging` environment the API **refuses to start** unless authentication is on, CORS is an explicit allow-list, the run store is durable, and (for live comms) a recipient-domain allow-list is set. This is intentional — it prevents an unsafe deploy.'),

  h2('Authentication & user management'),
  table(
    ['Item', 'Detail'],
    [
      ['**Provider**', 'Clerk (JWT). Turn it on with `AUTH_ENABLED=true` and set `CLERK_ISSUER`. Every `/v1/*` route then requires a verified bearer token.'],
      ['**Users & roles**', 'Managed in your Clerk dashboard (invite, deactivate, assign roles/organizations).'],
      ['**Tenant scoping**', 'A run is owned by the caller organization; one tenant can never read another. With auth on, a client-supplied `tenant_id` is ignored in favor of the token organization.'],
    ],
  ),

  h2('Notification settings (Email & Slack)'),
  table(
    ['Setting', 'Purpose'],
    [
      ['`GMAIL_SMTP_USER` / `GMAIL_SMTP_PASSWORD`', 'SMTP sender credentials (app password).'],
      ['`COMMS_AP_TEAM_MAILBOX`', 'BCC/Reply-To; gets a copy of every outbound mail.'],
      ['`COMMS_FINANCE_CONTROLLER_MAILBOX`', 'Where finance-note escalations go if Slack is off.'],
      ['`COMMS_TEST_RECIPIENT`', 'Dev safety net; if empty, an unresolved recipient is **skipped**, never guessed.'],
      ['`SLACK_WEBHOOK_URL`', 'Post finance-note / Slack drafts to a channel. If unset, they fall back to email.'],
    ],
  ),

  h2('Communication safety (live sending)'),
  p('Sending is **dry-run by default** (`COMMS_DRYRUN=true`) — drafts write a preview file instead of contacting a real recipient. To enable live sending:'),
  ol([
    'Set `COMMS_DRYRUN=false`.',
    'Set `COMMS_ALLOWED_DOMAINS` — a comma-separated allow-list of recipient domains. A live send to any other domain is **blocked**.',
    '(Recommended) Keep `COMMS_PER_DOMAIN_DAILY_CAP` — a per-domain daily send cap that guards against an escalation storm.',
    '(Recommended) Configure `VENDOR_MASTER_PATH` — a CSV mapping `vendor_name → email`. With a master configured, an **unknown vendor is refused**, not mis-delivered.',
  ]),

  h2('Workflow & routing settings'),
  table(
    ['Setting', 'Detail'],
    [
      ['**Resolution policy**', 'The routing rules and SLAs (see [Resolution Paths](/docs/resolution-paths)). First-match-wins; a catch-all is enforced at load time. Versioned by `policy version`.'],
      ['**Severity thresholds / priority weights**', 'Tunable per tenant (see [Severity & Priority](/docs/severity-priority)).'],
      ['**AI models**', 'Independently configurable per provider (classifier vs. drafter).'],
    ],
  ),

  h2('Import & durability settings'),
  table(
    ['Setting', 'Detail'],
    [
      ['**Max upload size**', '25 MB (`413` over the limit).'],
      ['`RUN_QUEUE_ENABLED`', 'Durable run execution (requires a database): runs survive restarts, crashed runs are re-leased and retried, work spreads across instances.'],
      ['`RUN_QUEUE_CONCURRENCY` / `RUN_QUEUE_LEASE_SECONDS` / `RUN_QUEUE_MAX_ATTEMPTS`', 'Tune the worker.'],
    ],
  ),

  h2('Persistence & retention'),
  table(
    ['Setting', 'Detail'],
    [
      ['`RUN_STORE_BACKEND`', '`auto | db | supabase | memory`. Use a durable backend in production; `memory` is dev-only and rejected by the production gate.'],
      ['`DATABASE_URL`', 'Apply schema with versioned Alembic migrations (`alembic upgrade head`); CI verifies up/down on every change.'],
      ['**Retention**', 'Set your retention window per your compliance policy. Audit events are append-only; export before purging (see [Compliance & Audit](/docs/compliance)).'],
    ],
  ),

  h2('Observability & ops'),
  table(
    ['Endpoint / setting', 'Purpose'],
    [
      ['`GET /healthz`', 'Liveness (process up).'],
      ['`GET /readyz`', 'Readiness — probes the store/DB; returns `503` if a dependency is down. Wire to your orchestrator.'],
      ['`GET /metrics`', 'Prometheus: runs, AI token usage + estimated cost, comms sends.'],
      ['`SENTRY_DSN`', 'Enable error tracking.'],
      ['`RATE_LIMIT_DEFAULT`', 'API rate limit (default `240/minute`).'],
    ],
  ),

  hr(),

  h2('Configuration reference (common variables)'),
  table(
    ['Variable', 'Default', 'Purpose'],
    [
      ['`ENVIRONMENT`', '`dev`', '`prod*`/`stag*` activate the safety gate.'],
      ['`AUTH_ENABLED`', '`false`', 'Require Clerk JWT on `/v1/*`.'],
      ['`CORS_ALLOW_ORIGINS`', '—', 'Explicit front-end origin(s) in prod.'],
      ['`RUN_STORE_BACKEND`', '`auto`', 'Operational store backend.'],
      ['`DATABASE_URL`', 'sqlite (dev)', 'Target DB.'],
      ['`RUN_QUEUE_ENABLED`', '`false`', 'Durable run execution.'],
      ['`COMMS_DRYRUN`', '`true`', 'Preview instead of live send.'],
      ['`COMMS_ALLOWED_DOMAINS`', '—', 'Live-send domain allow-list.'],
      ['`COMMS_PER_DOMAIN_DAILY_CAP`', '`25`', 'Escalation-storm guard.'],
      ['`VENDOR_MASTER_PATH`', '—', 'Vendor → email lookup.'],
      ['`RATE_LIMIT_DEFAULT`', '`240/minute`', 'API rate limit.'],
      ['`SENTRY_DSN`', '—', 'Error tracking.'],
    ],
  ),
  note('The console **Settings** page surfaces the non-secret subset live; secrets are never returned by the API.'),
];

export default blocks;
