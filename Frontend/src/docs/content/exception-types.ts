import { h1, h2, p, ul, table, note, hr, type Block } from '../blocks';

const blocks: Block[] = [
  h1('Exception Types'),
  p('The agent classifies every invoice into a **fixed taxonomy**. The classifier returns one primary type, a confidence score (0–1), and a plain-language rationale. Anything it cannot place confidently becomes **Other** and is sent to manual review.'),
  table(
    ['Type', 'Detected when…', 'Default route'],
    [
      ['**Price Variance**', 'Invoiced price/total differs from the PO.', 'Auto-approve / Manual / Escalate (by variance %)'],
      ['**Quantity Mismatch**', 'Invoiced quantity differs from the receipt.', 'Request GRN'],
      ['**Missing PO**', 'No purchase order is referenced.', 'Request PO'],
      ['**Duplicate**', 'The invoice appears to repeat a prior one.', 'Hold for investigation'],
      ['**Unapproved Vendor**', 'Vendor is not on the approved master.', 'Vendor validation review'],
      ['**GRN Not Received**', 'Goods receipt has not been posted.', 'Request GRN'],
      ['**Other**', 'The description does not fit any category.', 'Manual review'],
    ],
  ),
  note('*"High Severity"* and *"Auto-Resolvable"* are **not** exception types — they are outcomes. Severity is a separate dimension (see [Severity & Priority](/docs/severity-priority)); "auto-resolvable" means an exception routed to **Auto-approve**.'),

  hr(),

  h2('Price Variance'),
  p('**Definition** — the invoiced unit price or total differs from the agreed purchase-order price.'),
  p('**Business purpose** — protects margin: catches overbilling, expired contract pricing, and rate errors before payment.'),
  p('**Detection logic** — the classifier reads the description; a numeric variance percentage is parsed (e.g. "exceeds PO by 12%") and used by the routing rules to decide auto-approve vs. manual vs. escalate.'),
  p('**Common causes** — contract price not updated in the ERP, tiered/volume pricing applied incorrectly, currency rounding, freight/surcharge added to unit price.'),
  p('**Resolution** — small, in-tolerance variances auto-approve; material variances escalate to the Finance Controller; everything in between goes to manual review with a vendor clarification draft.'),

  h2('Quantity Mismatch'),
  p('**Definition** — the invoiced quantity differs from the quantity on the goods receipt.'),
  p('**Business purpose** — prevents paying for goods not received.'),
  p('**Common causes** — partial deliveries, receiving not fully posted, unit-of-measure mismatch (cases vs. eaches).'),
  p('**Resolution** — **Request GRN**: an internal note asks receiving/warehouse to confirm or correct the goods receipt before payment.'),

  h2('Missing PO'),
  p('**Definition** — the invoice references no purchase order.'),
  p('**Business purpose** — enforces the three-way match and PO-backed spend controls.'),
  p('**Common causes** — emergency/maverick spend, PO created after invoicing, data-entry omission.'),
  p('**Resolution** — **Request PO**: a vendor email requests the missing PO so the invoice can be matched.'),

  h2('Duplicate'),
  p('**Definition** — the invoice appears to repeat one already received.'),
  p('**Business purpose** — prevents double payment — a direct, recoverable cash loss.'),
  p('**Common causes** — vendor re-sends a reminder as a new invoice, EDI + email both ingested, statement re-billed.'),
  p('**Resolution** — **Hold for investigation** (no vendor contact): the item is held internally until a human confirms it is a true duplicate.'),

  h2('Unapproved Vendor'),
  p('**Definition** — the vendor is not present on the approved vendor master.'),
  p('**Business purpose** — fraud and compliance control; blocks payments to unvetted or spoofed payees.'),
  p('**Common causes** — new supplier not yet onboarded, name mismatch, potential vendor-impersonation fraud.'),
  p('**Resolution** — **Vendor validation review** (internal): routed to the vendor master team to validate and onboard, or reject.'),
  note('Verify bank-detail changes out of band, and require dual approval for new payees.'),

  h2('GRN Not Received'),
  p('**Definition** — the goods receipt note has not been posted for the invoiced items.'),
  p('**Business purpose** — enforces "pay on receipt".'),
  p('**Resolution** — **Request GRN**: internal note to receiving/warehouse to post or confirm the receipt.'),

  h2('Other'),
  p('**Definition** — the description does not match any category, or confidence is low.'),
  p('**Resolution** — **Manual review**. Low-confidence classifications (below 60%) always land here regardless of the suggested type, so a human makes the call. These are the items to staff first.'),
  ul([
    'Start your day with **Other** and low-confidence items — they need a human.',
    'Never send a suspected **Duplicate** to the vendor — it is held internally on purpose.',
  ]),
];

export default blocks;
