import { h1, h2, p, ul, ol, table, note, hr, type Block } from '../blocks';

const blocks: Block[] = [
  h1('Product Overview'),
  p('The **AP Exception Agent** is a human-in-the-loop platform that clears suspended Accounts Payable cash. You upload an exception queue; the agent classifies each invoice, routes it through your rules, drafts the vendor or controller communication, and records an audit trail. **You** review, approve, and release.'),
  note('**Design principle:** Use AI for ambiguity. Use deterministic code for certainty. Classification and drafting are AI. Severity, routing, prioritization, and persistence are deterministic, replayable, and auditable.'),

  h2('What it does'),
  table(
    ['Capability', 'What it means for you'],
    [
      ['**Detects exceptions**', 'Classifies messy ERP exception descriptions into a fixed taxonomy with a confidence score and a plain-language rationale.'],
      ['**Routes to resolution**', 'A deterministic rule engine picks the resolution path and SLA — identical inputs always reach the same outcome.'],
      ['**Drafts communications**', 'Generates vendor / internal / Slack / finance-controller messages, ready to edit and send. Nothing is sent automatically.'],
      ['**Prioritizes work**', 'Scores every exception by amount, age, severity, path, and confidence into a HIGH / MEDIUM / LOW queue.'],
      ['**Dashboards & analytics**', 'Suspended balance, breakdowns, vendor reliability, and an activity timeline.'],
      ['**Audit trail**', 'Append-only event log per run: what the agent saw, which rule fired, and the model + prompt version behind each decision.'],
    ],
  ),

  h2('Who it is for'),
  table(
    ['Audience', 'What they get'],
    [
      ['**AP Clerks**', 'A prioritized queue, drafted messages, and one-click clearing of routine exceptions.'],
      ['**AP Managers**', 'Throughput, SLA risk, and the ability to reassign or override.'],
      ['**Finance Controllers**', 'Escalations for high-value / high-severity items, with full rationale.'],
      ['**Procurement**', 'Vendor reliability profiles and recurring PO / GRN issues.'],
      ['**System Administrators**', 'Configuration, role and tenant management, notification and retention settings.'],
      ['**Developers**', 'A documented REST API to submit runs and read results.'],
      ['**Auditors**', 'Append-only logs, rule traces, and a deterministic decision path per invoice.'],
      ['**Implementation Partners**', 'A predictable rules engine and import format to map to a customer ERP.'],
    ],
  ),

  h2('How it works (in one minute)'),
  ol([
    '**Upload** a CSV or JSON exception queue (up to 25 MB).',
    'The agent **ingests** and validates each row; malformed rows are quarantined, not silently dropped.',
    'It **classifies** each exception (AI) and validates **severity** (deterministic thresholds).',
    'It **routes** each invoice to a resolution path (deterministic rules) with an SLA.',
    'Where communication is required, it **drafts** the message (AI) — vendor, internal, Slack, or finance note.',
    'It **prioritizes** every exception and writes the **audit trail**.',
    'You **review, edit, approve**, and release. Sends are explicit, never automatic.',
  ]),
  p('See [Architecture](/docs/architecture) for the full pipeline and [Quickstart](/docs/quickstart) to run it yourself.'),

  hr(),

  h2('What makes it audit-ready'),
  ul([
    '**Deterministic routing** — every resolution carries the matched rule ID, policy version, and a per-condition firing trace. Sufficient for a SOX walkthrough.',
    '**AI is contained** — only classification and drafting use a model, and tool-use is *forced*, so the model can never reply with free-form text in those nodes.',
    '**Severity is never AI-decided** — the suggestion is preserved separately (`severity_ai_suggested`) for drift monitoring, but the canonical `severity` is always set by deterministic thresholds.',
    '**PII redaction** — drafted messages run through a redaction pass (SSN-style, long card numbers, bank-account references) before they are stored.',
    '**Tenant isolation** — runs are scoped to your organization; one tenant can never read another tenant data.',
  ]),

  h2('Where AI is — and isn’t'),
  ul([
    '**AI:** classification of exception descriptions, and natural-language drafting of communications.',
    '**Deterministic:** ingestion, severity, routing rules, prioritization, persistence, and the audit log.',
  ]),
  p('If no AI provider key is configured, the platform runs in a **deterministic mock mode** end to end — useful for demos, development, and CI.'),
];

export default blocks;
