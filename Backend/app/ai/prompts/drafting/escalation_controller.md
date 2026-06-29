Channel: finance_note
Template ID: escalation_controller.v3

Draft a concise escalation to the Finance Controller regarding
{{invoice_id}} ({{vendor_name}}, {{invoice_amount}}). This text is delivered
to Slack (#ap-escalations) when configured, and to email otherwise — so keep
it self-contained and scannable.

# Subject
Use the format: `{{vendor_name}} {{invoice_id}} — {{exception_type}} ({{variance_pct}}%)`.
Example: `Workday INV-2005 — Price Variance (12%)`.
NEVER prefix with "Escalation:" — the channel header makes that obvious.

# Body
Write in this exact shape so it renders well as Slack bullets and as an email:

- **Greeting:** "Dear Finance Controller," (a single line)
- **One-line summary:** the bottom line — e.g. "{{vendor_name}} invoice
  {{invoice_id}} needs your approval: {{variance_pct}}% price variance
  ({{invoice_amount}})."
- **A blank line, then exactly these four bold-labelled bullets, in order:**
  - **Exposure:** {{vendor_name}} · {{invoice_id}} · {{invoice_amount}}
  - **Variance:** {{variance_pct}}% vs {{po_number}} (state the dollar gap)
  - **Root cause:** one short clause from context
  - **Recommended action:** approve / reject / request credit / hold
- **Deadline:** "Decision needed within {{sla_hours}} hours to release payment
  or open a vendor dispute."
- **Close:** "Thank you,"

Rules:
- Use Markdown `**bold**` for the four bullet labels and `- ` for the bullets.
- Lead with the dollar exposure — the controller scans this in ~30 seconds.
- Keep the whole body under 120 words. No tables, no headings, no links.
