import { h1, h2, p, table, code, warn, hr, type Block } from '../blocks';

const blocks: Block[] = [
  h1('Resolution Paths'),
  p('After classification, a **deterministic rule engine** decides what happens to each invoice. Rules are evaluated **top-down; first match wins**. A catch-all rule guarantees every invoice is routed. Each decision records the **matched rule ID, policy version, and a per-condition firing trace** — enough for a SOX walkthrough.'),
  warn('**Authoritative source.** The rules and thresholds below describe the **shipped default policy** (policy version 2026.05.1). Some onboarding decks quote rounder numbers (e.g. "auto-approve if confidence > 95% and amount < $5,000"). Where a deck and this page disagree, **this page and your deployed policy are authoritative** — confirm the live values in Settings → Config or via `GET /v1/config`. Thresholds are tunable per tenant.'),

  h2('The resolution paths'),
  table(
    ['Path', 'Outbound message?', 'Default SLA', 'Owner'],
    [
      ['**Auto-approve**', 'No', '24 h', 'System (no human needed)'],
      ['**Escalate to Controller**', 'Yes (finance note)', '8 h', 'Finance Controller'],
      ['**Manual Review**', 'Yes (vendor email)', '24 h', 'AP Clerk'],
      ['**Request PO**', 'Yes (vendor email)', '48 h', 'AP Clerk → Vendor'],
      ['**Request GRN**', 'Yes (internal email)', '48 h', 'Receiving / Warehouse'],
      ['**Hold for Investigation**', 'No', '24 h', 'AP Operations'],
      ['**Vendor Validation Review**', 'Yes (internal email)', '24 h', 'Vendor Master Team'],
    ],
  ),

  h2('Routing rules (first match wins)'),
  table(
    ['#', 'Rule ID', 'Conditions', '→ Path', 'SLA'],
    [
      ['1', '`pv_auto_approve_small`', 'Price Variance **and** variance `< 2%` **and** amount `< $10,000`', 'Auto-approve', '24 h'],
      ['2', '`pv_escalate_controller_high`', 'Price Variance **and** variance `≥ 5%`', 'Escalate to Controller', '8 h'],
      ['3', '`pv_manual_default`', 'Price Variance (any other)', 'Manual Review', '24 h'],
      ['4', '`missing_po_request`', 'Missing PO', 'Request PO', '48 h'],
      ['5', '`qty_mismatch_grn`', 'Quantity Mismatch', 'Request GRN', '48 h'],
      ['6', '`duplicate_hold`', 'Duplicate', 'Hold for Investigation', '24 h'],
      ['7', '`unapproved_vendor_validation`', 'Unapproved Vendor', 'Vendor Validation Review', '24 h'],
      ['8', '`grn_missing_request`', 'GRN Not Received', 'Request GRN', '48 h'],
      ['9', '`low_confidence_manual`', 'Classifier confidence `< 0.60`', 'Manual Review', '24 h'],
      ['10', '`default_manual`', '*(catch-all — empty condition)*', 'Manual Review', '72 h'],
    ],
  ),
  p('**Reading the table:** because evaluation stops at the first match, ordering matters. A 6% Price Variance matches rule 2 (escalate) before it can reach rule 3. A Duplicate with 0.4 confidence matches rule 6 (hold) before rule 9 — the type-specific rule wins because it comes first.'),

  h2('Decision tree'),
  code('text', `
Is it a Price Variance?
├─ yes → variance < 2% AND amount < $10k? ── yes → AUTO-APPROVE (24h)
│         └─ no → variance >= 5%? ── yes → ESCALATE TO CONTROLLER (8h)
│                  └─ no → MANUAL REVIEW (24h)
└─ no → Missing PO?            → REQUEST PO (48h)
        Quantity Mismatch?     → REQUEST GRN (48h)
        Duplicate?             → HOLD FOR INVESTIGATION (24h)
        Unapproved Vendor?     → VENDOR VALIDATION REVIEW (24h)
        GRN Not Received?      → REQUEST GRN (48h)
        confidence < 0.60?     → MANUAL REVIEW (24h)
        otherwise              → MANUAL REVIEW (72h, catch-all)
`),

  h2('Example scenarios'),
  p('**Scenario A — routine price variance, auto-cleared.** Workday invoice, 1.2% over PO, $4,800. → Rule 1 → **Auto-approve**, no message, 24 h SLA. The clerk never touches it.'),
  p('**Scenario B — material variance, escalated.** Snowflake invoice, 12% over PO, $27,500. → Rule 2 → **Escalate to Controller**, finance-note draft, 8 h SLA.'),
  p('**Scenario C — missing PO.** New SaaS vendor billed on account, no PO. → Rule 4 → **Request PO**, vendor-email draft, 48 h SLA.'),
  p('**Scenario D — suspected duplicate.** Same invoice number + amount as 6 days ago. → Rule 6 → **Hold for Investigation**, no vendor contact, 24 h SLA.'),
  p('**Scenario E — ambiguous description.** Classifier returns "Other" at 0.45 confidence. → Rule 9 → **Manual Review**, 24 h SLA.'),

  h2('Communications by path'),
  p('When a path requires an outbound message, the **channel, recipient, and template** are chosen deterministically; only the wording is AI-generated:'),
  table(
    ['Path', 'Channel', 'Template'],
    [
      ['Escalate to Controller', 'Finance note (Slack or email)', 'Controller escalation'],
      ['Manual Review (Price Variance)', 'Vendor email', 'Price-variance clarification'],
      ['Request PO', 'Vendor email', 'Missing-PO request'],
      ['Request GRN (Quantity Mismatch)', 'Vendor email', 'Quantity-mismatch clarification'],
      ['Request GRN (GRN Not Received)', 'Internal email', 'GRN-missing request'],
      ['Hold for Investigation', 'Internal email', 'Duplicate hold'],
      ['Vendor Validation Review', 'Internal email', 'Unapproved-vendor review'],
    ],
  ),
  hr(),
  p('All sends are **dry-run by default** and require explicit human action. See [Administrator Guide](/docs/admin-guide) to enable live sending with a recipient-domain allowlist and a per-domain daily cap.'),
];

export default blocks;
