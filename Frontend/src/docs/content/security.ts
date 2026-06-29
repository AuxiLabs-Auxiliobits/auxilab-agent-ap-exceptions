import { h1, h2, p, ul, type Block } from '../blocks';

const blocks: Block[] = [
  h1('Security'),
  p('How the platform protects your data and controls access. This page is written for security reviewers and system administrators.'),

  h2('Authentication & access control'),
  ul([
    '**Identity:** Clerk-issued **JWT** bearer tokens on every `/v1/*` route (when `AUTH_ENABLED=true`). Tokens are verified against the configured issuer/JWKS.',
    '**Authorization:** runs are **owned by the caller organization (tenant)**. Read/write is scoped to that tenant.',
    '**No enumeration:** accessing a run you do not own returns `404`, not `403`, so existence is not leaked across tenants.',
    '**Production gate:** the API refuses to boot in `production`/`staging` if auth is off, CORS is open, the store is non-durable, or live comms have no allow-list.',
  ]),

  h2('Tenant isolation'),
  p('Every run carries a `tenant_id`. All reads and writes filter by the authenticated tenant, so one organization can never see another results, drafts, vendors, or audit logs. With auth on, a client-supplied `tenant_id` is ignored in favor of the token organization.'),

  h2('File-upload security'),
  ul([
    '**Size cap:** 25 MB (`413` over the limit) — a defensive memory bound.',
    '**CSV-injection neutralization:** cells starting with `=`, `+`, `-`, or `@` are sanitized, so a malicious export cannot execute a spreadsheet formula downstream.',
    '**Validation & quarantine:** malformed rows are quarantined with a reason code, never silently executed.',
    '**No code execution:** uploads are parsed as data (CSV/JSON) only.',
  ]),

  h2('Prompt-injection defense'),
  p('User-supplied free text (the exception description) is wrapped in `<exception>` / `<context>` delimiters, and the system prompt instructs the model to treat the contents as **data, not instructions**. Combined with **forced tool-use** (the model must return structured output and cannot emit free-form text in the classify/draft nodes), this contains prompt-injection attempts.'),

  h2('PII handling & data protection'),
  ul([
    '**Redaction:** drafted messages pass through a redaction pass — SSN-style patterns, long card-like numbers, and bank-account references are replaced before the draft is persisted.',
    '**Secrets:** API keys and credentials are read from environment configuration and **never returned** by the API (`/v1/config` exposes only non-secret values).',
    '**In transit:** serve the API and console over TLS; the console talks to the API same-origin via the reverse proxy.',
    '**At rest:** data is stored in your configured database; apply your platform encryption-at-rest.',
  ]),

  h2('API security'),
  ul([
    '**Rate limiting:** default `240/minute` per client (`429` over the limit).',
    '**CORS:** an explicit origin allow-list in production (no wildcard).',
    '**Security headers:** the console is served with CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, and HSTS.',
    '**Forced tool-use** on AI calls eliminates free-text model responses in the pipeline.',
  ]),

  h2('Communication safety'),
  ul([
    '**Dry-run by default** — drafts never reach a real recipient until live sending is explicitly enabled.',
    '**Domain allow-list** — live sends are restricted to approved recipient domains.',
    '**Per-domain daily cap** — guards against a runaway escalation storm.',
    '**Unknown-vendor refusal** — with a vendor master configured, a vendor not on it is refused rather than mis-delivered.',
  ]),

  h2('Disaster recovery & backups'),
  ul([
    '**Durable run store** — runs persist to your database and survive restarts.',
    '**Durable run queue (optional)** — the uploaded input is persisted; a crashed run is re-leased and retried, and orphaned work is reclaimed on startup.',
    '**Backups** — back up the database on your standard schedule; the schema is migration-versioned (Alembic) so a restore is reproducible.',
    '**Graceful shutdown** — in-flight runs are drained on shutdown before the process exits.',
    '**Health probes** — `/readyz` gates traffic on dependency health so an unhealthy instance is not routed to.',
  ]),

  h2('Responsible disclosure'),
  p('Found a vulnerability? Contact your platform administrator or the security contact for your deployment. Please do not post details publicly until a fix is available.'),
];

export default blocks;
