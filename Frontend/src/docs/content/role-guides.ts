import { h1, h2, p, ol, ul, tip, hr, type Block } from '../blocks';

const blocks: Block[] = [
  h1('Role Guides'),
  p('Day-in-the-life workflows for each role. Each guide is a short, repeatable routine plus the screens you live in.'),

  hr(),

  h2('AP Clerk'),
  p('**Goal:** clear the most exceptions correctly, fastest.'),
  ol([
    'Open **Priority** → work the **HIGH** bucket top-down.',
    'For each item, check **Classification** (type, confidence, rationale).',
    'Go to **Communications** → read the drafted message, edit if needed, **send** (or queue for send).',
    'Auto-approve items need no action — confirm them in **Resolution**.',
    'Anything you are unsure of → leave a note / reassign to your manager.',
  ]),
  tip('Start with low-confidence items (they need a human); never send a suspected **Duplicate** to the vendor (it is held internally on purpose).'),

  h2('AP Manager'),
  p('**Goal:** throughput, SLA, and quality.'),
  ol([
    '**Dashboard** → watch SLA-at-risk count and escalations.',
    '**Analytics** → spot a rising exception type or a slipping confidence trend.',
    'Rebalance the team against the **Priority** queue.',
    'If escalations dominate, review your variance thresholds with the Controller (see [Resolution Paths](/docs/resolution-paths)).',
    'Approve completed runs.',
  ]),
  tip('Use **Vendors** to find the suppliers generating the most rework and push root-cause fixes upstream.'),

  h2('Finance Controller'),
  p('**Goal:** decide on the high-value / high-severity items only.'),
  ol([
    '**Dashboard** → open **Escalations required**, or filter **Resolution** to `ESCALATE_CONTROLLER`.',
    'Read the AI **rationale** and the **rule trace** — you see exactly why it escalated.',
    'Approve, reject, or request a credit note. The **finance-note** draft is pre-written for you.',
    'Confirm the action is captured in the **audit log**.',
  ]),
  tip('Escalations carry an **8-hour SLA** by default; they sort to the top of your queue.'),

  h2('Procurement Team'),
  p('**Goal:** fix recurring PO / GRN / vendor problems at the source.'),
  ol([
    '**Vendors** → sort by exception count and reliability score.',
    'Identify patterns: chronic **Missing PO**, repeated **Quantity Mismatch**, **Unapproved Vendor** hits.',
    'Drive upstream fixes: PO discipline, receiving timeliness, vendor onboarding.',
    'Use **Analytics** to show improvement quarter over quarter.',
  ]),

  h2('Auditor'),
  p('**Goal:** verify that every payment decision is explainable and controlled.'),
  ol([
    'Pick any run → **Resolution** → open an invoice **rule trace** (conditions evaluated + the rule that matched, with policy version).',
    '**Classification** → confirm the model id + prompt version stamped on the decision.',
    '**Audit log** (`GET /v1/runs/{id}/audit`) → walk the append-only event sequence: ingest → classify → route → draft → persist.',
    'Confirm **no automatic sends** occurred without human approval (`is_edited_by_human` / send status).',
    'Confirm **severity** was set deterministically (compare `severity` vs. `severity_ai_suggested`).',
  ]),
  ul([
    'Routing is deterministic and reproducible; the audit log is append-only; tenant isolation prevents cross-org reads. See [Compliance & Audit](/docs/compliance).',
  ]),
];

export default blocks;
