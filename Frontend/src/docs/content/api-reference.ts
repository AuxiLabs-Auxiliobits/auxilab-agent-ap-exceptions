import { h1, h2, p, ul, table, code, hr, type Block } from '../blocks';

const blocks: Block[] = [
  h1('API Reference'),
  p('A REST API to submit exception queues and read results. JSON over HTTPS. All business endpoints live under `/v1`.'),
  ul([
    '**Base URL:** your deployment origin (e.g. `https://api.example.com`). The console proxies `/v1` to the API so the browser uses one origin.',
    '**Content type:** `application/json` (uploads use `multipart/form-data`).',
  ]),

  h2('Authentication'),
  p('When auth is enabled, every `/v1/*` request requires a **Clerk JWT** as a bearer token:'),
  code('text', `Authorization: Bearer <jwt>`),
  ul([
    'Runs are **scoped to the token organization** (tenant). You can only read your own org runs.',
    'A missing/invalid token returns `401`. Accessing another tenant run returns `404` (not `403`, to avoid leaking existence).',
    'Health (`/healthz`, `/readyz`) and `/metrics` are unauthenticated.',
  ]),

  h2('Rate limits'),
  p('Default **240 requests/minute** per client (configurable). Exceeding it returns `429 Too Many Requests`. Submitting a run is asynchronous, so you poll rather than hold a connection.'),

  h2('Endpoints'),
  table(
    ['Method', 'Path', 'Purpose'],
    [
      ['`POST`', '`/v1/runs`', 'Upload a CSV/JSON queue and start a run.'],
      ['`GET`', '`/v1/runs`', 'List runs (newest first) for your tenant.'],
      ['`GET`', '`/v1/runs/{id}`', 'Run status + quarantine/error summary.'],
      ['`GET`', '`/v1/runs/{id}/results`', 'Per-invoice classification, resolution, draft.'],
      ['`GET`', '`/v1/runs/{id}/metrics`', 'Dashboard metrics + priority queues.'],
      ['`GET`', '`/v1/runs/{id}/audit`', 'Append-only audit log.'],
      ['`GET`', '`/v1/runs/{id}/drafts/{invoice_id}`', 'Fetch one draft.'],
      ['`PATCH`', '`/v1/runs/{id}/drafts/{invoice_id}`', 'Edit a draft subject/body.'],
      ['`POST`', '`/v1/runs/{id}/drafts/{invoice_id}/send`', 'Send one draft.'],
      ['`POST`', '`/v1/runs/{id}/drafts/send_all`', 'Bulk-send selected drafts.'],
      ['`GET`', '`/v1/runs/{id}/sent`', 'Send results for the run.'],
      ['`POST`', '`/v1/runs/{id}/approve`', 'Mark the run `COMPLETED`.'],
      ['`GET`', '`/v1/vendors`', 'Vendor reliability profiles.'],
      ['`GET`', '`/v1/config`', 'Non-secret runtime configuration.'],
      ['`GET`', '`/v1/upload/format`', 'Accepted columns, types, aliases, limits.'],
      ['`GET`', '`/v1/upload/template.csv`', 'Download the CSV template.'],
      ['`GET`', '`/v1/runs/{id}/rejections.csv`', 'Rejected-rows report.'],
      ['`GET`', '`/healthz`, `/readyz`, `/metrics`', 'Liveness, readiness, Prometheus metrics.'],
    ],
  ),

  h2('Create a run'),
  code('bash', `
curl -X POST https://api.example.com/v1/runs \\
  -H "Authorization: Bearer $TOKEN" \\
  -F "file=@exceptions.csv" \\
  -F "tenant_id=acme"
`),
  p('**Response `200`** — returns immediately; the run executes in the background.'),
  code('json', `
{
  "run_id": "run_8f3c0a1b2c3d",
  "tenant_id": "acme",
  "status": "PENDING",
  "created_at": "2026-06-16T09:41:02Z",
  "rows_accepted": 0,
  "rows_quarantined": 0,
  "current_node": "START"
}
`),
  p('Poll `GET /v1/runs/{id}` until `status` is terminal: `AWAITING_REVIEW`, `COMPLETED`, or `FAILED`. Lifecycle: `PENDING → RUNNING → AWAITING_REVIEW → COMPLETED` (or `FAILED`).'),

  h2('Get results'),
  code('bash', `
curl https://api.example.com/v1/runs/run_8f3c0a1b2c3d/results \\
  -H "Authorization: Bearer $TOKEN"
`),
  code('json', `
{
  "run_id": "run_8f3c0a1b2c3d",
  "count": 10,
  "results": [
    {
      "invoice_id": "INV-2001",
      "classification": { "primary_exception_type": "Price Variance", "severity": "HIGH", "confidence_score": 0.92 },
      "resolution": { "resolution_path": "ESCALATE_CONTROLLER", "rule_id": "pv_escalate_controller_high", "sla_hours": 8 },
      "draft": { "channel": "finance_note", "send_status": "draft" }
    }
  ]
}
`),

  h2('Edit and send a draft'),
  code('bash', `
# Edit
curl -X PATCH .../v1/runs/run_8f3c/drafts/INV-2001 \\
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \\
  -d '{"subject":"Workday INV-2001 review","body":"Hi team, ..."}'

# Send (dry-run unless live sending is configured)
curl -X POST .../v1/runs/run_8f3c/drafts/INV-2001/send \\
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{}'
`),
  p('`send` returns a `SendResult` with `status` in `sent | dryrun | failed | skipped`, plus `provider`, `message_id`, `recipient`, and any `error_message`.'),

  h2('Error codes'),
  table(
    ['Status', 'Meaning'],
    [
      ['`400`', 'Bad request — missing/empty file, invalid body.'],
      ['`401`', 'Missing or invalid bearer token.'],
      ['`404`', 'Run/draft/vendor not found — **or** not owned by your tenant.'],
      ['`413`', 'Upload exceeds the 25 MB limit.'],
      ['`422`', 'Validation error (e.g. draft body too long).'],
      ['`429`', 'Rate limit exceeded.'],
      ['`503`', 'Not ready — a dependency (store/DB) is down (`/readyz`).'],
    ],
  ),
  p('Error bodies use `{ "detail": "<message>" }`.'),

  hr(),

  h2('Notes for integrators'),
  ul([
    '**Idempotency of sends** — a draft already `sent`/`dryrun` returns its prior result instead of double-sending.',
    '**Determinism** — re-running the same input under the same policy version yields identical routing and severity.',
    '**Pagination** — `GET /v1/runs` returns your tenant runs newest-first as `{ "runs": [...], "total": N }`.',
    '**Webhooks** — there is no push API today; poll run status or query the metrics endpoint.',
  ]),
];

export default blocks;
