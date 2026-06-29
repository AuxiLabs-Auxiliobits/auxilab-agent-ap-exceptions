import { h1, h2, p, ul, table, note, hr, type Block } from '../blocks';

const blocks: Block[] = [
  h1('Dashboards'),
  p('The console is organized as a set of screens, each answering one question. This page documents every screen: its **purpose, metrics, calculations, filters, and actions**.'),
  note('**Naming note:** some materials refer to a *"Clearing Desk"* or *"Resolution Dashboard."* In this console those map to **Dashboard** (the clearing desk) and **Resolution** respectively. The table below uses the names you see in the sidebar.'),
  table(
    ['Screen', 'Answers'],
    [
      ['**Dashboard**', 'Where is my cash stuck, and what should I clear first?'],
      ['**Queue**', 'What got ingested, and what was quarantined?'],
      ['**Classification**', 'What is each exception, and how sure are we?'],
      ['**Resolution**', 'Which path did each invoice take, and why?'],
      ['**Communications**', 'What will we say to vendors / controllers, and has it been sent?'],
      ['**Priority**', 'In what order should we work?'],
      ['**Vendors**', 'Which suppliers cause the most exceptions?'],
      ['**Analytics**', 'How are we trending?'],
    ],
  ),

  hr(),

  h2('Dashboard (Clearing Desk)'),
  p('**Purpose** — the home screen and command center for a run.'),
  ul([
    '**Suspended balance** — total exception value, split into at-risk, escalated, awaiting review, and cleared.',
    '**Total exceptions**, **auto-resolvable count**, **escalations required**, **SLA-at-risk count**, **average confidence**.',
    '**Breakdown charts** — by type, severity, and resolution path.',
    '**Top actionable** — the highest-priority items.',
  ]),
  p('**Calculations** — values come from `GET /v1/runs/{id}/metrics`; auto-resolvable = items routed to Auto-approve; escalations = items routed to Escalate to Controller; SLA-at-risk derived from `days_outstanding` vs. the path SLA. **Filters:** by run. **Actions:** upload a new queue; open any item; jump to Communications.'),

  h2('Queue'),
  p('**Purpose** — ingestion results, including what was **quarantined**. **Metrics:** rows accepted vs. quarantined. The **Quarantined panel** lists every rejected row with its row index, raw values, and reason code. **Actions:** download the rejection report (`rejections.csv`), fix, and re-upload.'),

  h2('Classification'),
  p('**Purpose** — review what the AI decided for each invoice. **Columns:** exception type, **confidence** bar, severity, and the **rationale**. **Filters:** by type, severity, confidence band. **Actions:** open an item to read the full rationale; low-confidence (`< 0.60`) items are flagged for manual review.'),

  h2('Resolution'),
  p('**Purpose** — the deterministic outcome per invoice. **Columns:** resolution path, **rule ID**, **policy version**, **SLA**, and whether a communication is required. The **rule trace** shows the ordered conditions evaluated and the one that matched — the auditable "why." **Actions:** open the rule trace; jump to the draft.'),

  h2('Communications'),
  p('**Purpose** — review, edit, and send the drafted messages. **Channels:** Vendor email, Internal email, Slack, Finance note. **Per draft:** recipient, subject, body, template ID, and **send status** (`draft`, `dryrun`, `sent`, `failed`, `skipped`).'),
  ul([
    '**Edit** a draft (flagged `is_edited_by_human`).',
    '**Send** one, or **Send all** selected.',
    'In **dry-run** (default), sending writes a preview file instead of contacting a real recipient.',
  ]),

  h2('Priority'),
  p('**Purpose** — the work order. A Kanban of HIGH / MEDIUM / LOW buckets. **Per card:** invoice, vendor, amount, severity, **priority score**, and the **drivers** that pushed it up (amount, age, severity, path, confidence). See [Severity & Priority](/docs/severity-priority). **Actions:** work top-down within a bucket.'),

  h2('Vendors'),
  p('**Purpose** — supplier reliability over time, accumulated across runs. **Per vendor:** invoices seen, total amount processed, counts of duplicates / missing-PO / unapproved / escalations / auto-approvals, average days outstanding, average confidence, and a **reliability score** in `[0,1]`. **Use it for** quarterly business reviews and targeting recurring root causes.'),

  h2('Analytics'),
  p('**Purpose** — trends and distributions across the run. **Charts:** exception value over time, breakdown by type/severity/path, confidence distribution. **Actions:** export views for reporting.'),

  h2('Slack notifications'),
  p('Slack is a **communication channel**, not a screen. When a Slack webhook is configured, **finance-note** and Slack-channel drafts post to your chosen channel (e.g. `#ap-escalations`). If Slack is not configured, those messages **fall back to email** to the finance-controller / AP mailbox with a clear subject prefix, so nothing is lost. Configure it in [Administrator Guide](/docs/admin-guide).'),
];

export default blocks;
