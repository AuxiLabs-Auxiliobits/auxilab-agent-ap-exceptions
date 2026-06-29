import { h1, h2, p, ul, table, code, note, type Block } from '../blocks';

const blocks: Block[] = [
  h1('Severity & Priority'),
  p('Two independent dimensions drive triage: **severity** (how risky an exception is) and **priority** (what to work first). Both are **deterministic** — no AI sets them.'),

  h2('Severity (deterministic thresholds)'),
  p('The AI may *suggest* a severity, but the canonical `severity` is always computed by fixed thresholds and stored alongside the AI suggestion (`severity_ai_suggested`) for drift monitoring.'),
  table(
    ['Severity', 'Rule'],
    [
      ['**HIGH**', '`amount > $25,000` **OR** `days_outstanding > 30`'],
      ['**MEDIUM**', '`$5,000 ≤ amount ≤ $25,000`'],
      ['**LOW**', '`amount < $5,000`'],
    ],
  ),
  note('**Why deterministic?** Severity affects escalation and SLA. Tying it to fixed, auditable thresholds means it is reproducible and defensible — the same invoice always gets the same severity.'),

  h2('Priority score'),
  p('Every exception gets a single priority score in `[0, 1]`, then a bucket. The score is a weighted blend:'),
  code('text', `
priority_score =
    w_amount   x normalize(invoice_amount, 0 ... 100,000)
  + w_age      x normalize(days_outstanding, 0 ... 60)
  + w_severity x severity_weight
  + w_path     x resolution_path_weight
  + w_conf     x (1 - confidence_score)
`),
  p('**Default weights**'),
  table(
    ['Weight', 'Default', 'Drives'],
    [
      ['`w_amount`', '0.30', 'Bigger dollars first.'],
      ['`w_age`', '0.25', 'Older exceptions first.'],
      ['`w_severity`', '0.25', 'HIGH severity floats up.'],
      ['`w_path`', '0.15', 'Riskier paths (escalate, hold) rank higher.'],
      ['`w_conf`', '0.05', 'Lower confidence gets attention (`1 - confidence`).'],
    ],
  ),
  p('Weights are **tunable per tenant**. Higher inputs always raise the score, so the queue reflects real business risk, not model whim.'),

  h2('Buckets'),
  table(
    ['Bucket', 'Rule'],
    [
      ['**HIGH**', '`score ≥ 0.70` **or** `severity == HIGH`'],
      ['**MEDIUM**', '`0.40 ≤ score < 0.70`'],
      ['**LOW**', '`score < 0.40`'],
    ],
  ),
  p('A HIGH-severity item is **always** at least HIGH priority, even if its numeric score is lower — risk overrides arithmetic.'),

  h2('Tie-breaking'),
  p('When scores tie, the queue orders by:'),
  code('text', `(-score, -days_outstanding, -amount, invoice_id)`),
  p('So among equal scores, the older and larger items come first, with the invoice ID as a final deterministic tiebreaker — the ordering is **stable and reproducible** across runs.'),

  h2('How to use it'),
  ul([
    '**AP Clerks** — work the HIGH bucket top-down; it already reflects amount, age, severity, path, and confidence.',
    '**AP Managers** — if escalations dominate, tune `w_path`/`w_severity`. If aged items slip, raise `w_age`.',
    '**Auditors** — every score is reproducible from the inputs and the published weights; there is no randomness.',
  ]),
];

export default blocks;
