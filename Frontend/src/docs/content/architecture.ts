import { h1, h2, h3, p, ul, ol, table, code, note, hr, type Block } from '../blocks';

const blocks: Block[] = [
  h1('Architecture'),
  p('The platform is a **LangGraph-orchestrated pipeline** with selective AI nodes. Each invoice flows through the same ordered stages; state is checkpointed after every stage so progress is observable and runs are recoverable.'),

  h2('The pipeline'),
  code('text', `
ingest ─► classify (AI) ─► severity ─► route (rules)
                                          │
                   ┌──────────────────────┤
                   ▼                      ▼
              draft (AI)             prioritize
                   │                      │
                   └──────────┬───────────┘
                              ▼
                          persist ─► review
`),
  table(
    ['Stage', 'Type', 'What it does'],
    [
      ['**ingest**', 'Deterministic', 'Parse CSV/JSON, map columns (with aliases), validate, quarantine bad rows.'],
      ['**classify**', '**AI**', 'Assign an exception type + confidence + rationale. Tool-use is forced.'],
      ['**severity**', 'Deterministic', 'Set the canonical severity from amount/age thresholds.'],
      ['**route**', 'Deterministic', 'First-match-wins rule engine → resolution path + SLA + rule trace.'],
      ['**draft**', '**AI**', 'Generate the vendor/internal/Slack/finance message (only when routing requires it).'],
      ['**prioritize**', 'Deterministic', 'Weighted score → HIGH/MEDIUM/LOW priority queue.'],
      ['**persist**', 'Deterministic', 'Write the run snapshot + append-only audit log.'],
    ],
  ),

  h2('Where AI is — and isn’t'),
  ul([
    '**AI nodes:** `classify` and `draft`. Both use **forced tool-use**, so the model must return structured output — it can never reply with free text. The same tool schema is translated to each provider native shape, so downstream stages never see provider-specific output.',
    '**Everything else is deterministic** and replayable. Given the same input and policy version, routing, severity, prioritization, and the audit trail are identical every time.',
  ]),

  h3('AI providers'),
  p('The AI client selects a backend at startup by precedence:'),
  ol([
    '**Anthropic Claude** (preferred) — if an Anthropic key is set.',
    '**Google Gemini** — fallback.',
    '**Azure OpenAI** — fallback.',
    '**Deterministic mock mode** — if no key is set. The full pipeline still runs end to end (useful for dev, CI, and demos).',
  ]),

  h2('Determinism & auditability'),
  ul([
    'The model **severity suggestion** is recorded as `severity_ai_suggested` for drift monitoring, but the canonical `severity` is **always** the deterministic threshold result.',
    'Every routing decision carries the **matched rule ID**, **policy version**, and a **per-condition firing trace**.',
    'User free text is wrapped in `<exception>` / `<context>` delimiters and treated as **data, not instructions** (prompt-injection defense).',
    'Drafted outputs pass through a **PII redaction** step before persistence.',
  ]),

  h2('Run execution & durability'),
  p('A submitted run executes asynchronously and **checkpoints state to the store after every stage**, so polling clients see live progress (`current_node`, accumulating counts).'),
  p('For production, the platform supports a **durable run queue**: the uploaded input is persisted and a worker leases and executes it, so a run **survives a restart**, a crashed run is **re-leased and retried**, and the work can be spread across **multiple instances**. See the [Administrator Guide](/docs/admin-guide) for enabling it.'),

  h2('Persistence'),
  ul([
    '**Run store** — the operational store the console reads/writes on every step. Backends: a SQL database (recommended, durable), a hosted Postgres/REST store, or in-memory (dev only).',
    '**Normalized tables** — a relational schema (exceptions, classifications, resolutions, communications, status history, priorities, vendors, agent executions) managed with versioned **Alembic** migrations.',
    '**Audit log** — append-only events per run.',
  ]),

  h2('Deployment shape'),
  ul([
    'A **REST API** serves all `/v1/*` endpoints plus health/readiness probes and a Prometheus `/metrics` endpoint.',
    'The **React console** is served by a static host / reverse proxy that forwards `/v1`, `/healthz`, and `/readyz` to the API, so the browser talks to a single origin.',
    'Health is split into **liveness** (`/healthz`, process up) and **readiness** (`/readyz`, probes the store/DB and returns 503 if a dependency is down).',
  ]),

  hr(),
  note('Want the data model? The normalized schema and migration strategy are summarized in [Compliance & Audit](/docs/compliance) and the [Administrator Guide](/docs/admin-guide).'),
];

export default blocks;
