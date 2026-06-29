import { h1, h2, p, ul, table, note, type Block } from '../blocks';

const blocks: Block[] = [
  h1('Compliance & Audit'),
  p('The platform is built so that **every payment-affecting decision is explainable, reproducible, and recorded** — the properties auditors and finance-controls teams need.'),

  h2('Audit trail'),
  p('Each run writes an **append-only** event log. Events are added, never edited.'),
  ul([
    'Pipeline events per stage: `NODE_START` / `NODE_END`, `AI_CALL`, `ERROR`, approvals, human edits.',
    'For classifications: the **model id** and **prompt version** that produced the result.',
    'For routing: the **matched rule id**, **policy version**, and the **per-condition rule trace**.',
    'For sends: status, provider, recipient, and message id.',
  ]),
  p('**Access** — `GET /v1/runs/{id}/audit`, or the **Audit** view in the console.'),

  h2('Deterministic, reproducible decisions'),
  ul([
    '**Routing** is first-match-wins over a versioned policy. Given the same inputs and policy version, the resolution path, SLA, and rule trace are identical every time.',
    '**Severity** is set by fixed thresholds (never by AI). The AI suggestion is retained separately (`severity_ai_suggested`) for drift monitoring only.',
    '**Priority** is a published weighted formula with deterministic tie-breaking — no randomness.',
  ]),
  p('This means an auditor can **re-derive any decision** from the recorded inputs.'),

  h2('SOX considerations'),
  table(
    ['Control objective', 'How the platform supports it'],
    [
      ['**Authorization of disbursements**', 'No automatic sends or approvals; a human reviews, edits, and approves. Approval is recorded in the audit log.'],
      ['**Segregation of duties**', 'Roles (Clerk, Manager, Controller) via your identity provider; escalations route high-value items to the Controller.'],
      ['**Completeness & accuracy**', 'Malformed rows are quarantined (not dropped) with a rejection report; counts reconcile (accepted + quarantined = submitted).'],
      ['**Traceability**', 'Rule trace + model/prompt version + append-only log give a full path from invoice to outcome.'],
      ['**Change management**', 'Policy and schema are versioned; DB migrations are reviewed and applied via Alembic with CI verifying up/down.'],
    ],
  ),
  note('This describes control *support*, not a certification. Your SOX program owner determines control design and operating effectiveness for your environment.'),

  h2('Finance controls'),
  ul([
    '**Three-way-match support** — Missing-PO and GRN exceptions route to PO/receipt requests before payment.',
    '**Duplicate prevention** — suspected duplicates are held for investigation and never auto-contacted or paid.',
    '**Vendor risk** — Unapproved-Vendor exceptions route to a validation review; the vendor-master allow-list refuses unknown payees on live sends.',
    '**Spend escalation** — high-value / high-severity items escalate to the Controller with a short SLA.',
  ]),

  h2('Operational controls'),
  ul([
    '**Idempotent sends** — a draft already sent returns its prior result; no double-send.',
    '**Live-send guardrails** — dry-run default, domain allow-list, per-domain daily cap.',
    '**Observability** — health/readiness probes, Prometheus metrics (including AI token cost), and structured logs with per-request correlation ids.',
    '**Recoverability** — durable run store and optional durable queue with retry and orphan reclaim.',
  ]),

  h2('Data retention & residency'),
  ul([
    'Run snapshots and audit events persist in your database until your retention policy purges them.',
    'Audit events are **append-only**; export them (e.g. to a warehouse or archive) **before** any purge to preserve the record.',
    'Data lives in **your** configured database/region. The platform does not require sending invoice data to any third party other than the AI provider you configure (or none, in deterministic mock mode).',
  ]),
];

export default blocks;
