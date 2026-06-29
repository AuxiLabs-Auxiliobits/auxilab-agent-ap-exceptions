import { h1, h2, p, code, note, type Block } from '../blocks';

const blocks: Block[] = [
  h1('Sample Data'),
  p('Copy-paste-ready samples for testing an upload, an integration, or a demo.'),
  note('The console ships with a built-in sample queue you can upload directly, and a **Download CSV template**. The data below mirrors that sample.'),

  h2('Sample CSV'),
  p('A balanced 10-row queue covering every exception type. Save as `exceptions.csv` and upload it.'),
  code('csv', `
invoice_id,vendor_name,invoice_amount,po_number,exception_type,exception_description,days_outstanding
INV-2001,Workday,27500,PO-8841,Price Variance,Invoice exceeds PO by 12% on three line items,14
INV-2002,Oracle,4800,PO-8842,Price Variance,Unit price 1.2% above contract baseline,3
INV-2003,Acme Freight,15200,,Missing PO,No purchase order referenced on the invoice,21
INV-2004,Snowflake,36000,PO-8850,Price Variance,Material 18% variance versus contracted rate,33
INV-2005,Globex Supplies,9120,PO-8851,Quantity Mismatch,Invoiced qty 120 vs goods receipt qty 100,9
INV-2006,Initech,4200,PO-8852,Duplicate,Same invoice number and amount submitted six days ago,6
INV-2007,Umbrella Corp,52000,,Unapproved Vendor,Payee not present in the vendor master,2
INV-2008,Stark Industrial,18750,PO-8853,GRN Not Received,Goods receipt has not been posted,12
INV-2009,Wayne Logistics,2100,PO-8854,Price Variance,Freight surcharge added to unit price 0.9%,1
INV-2010,Cyberdyne,8800,PO-8855,Quantity Mismatch,Partial delivery 40 of 100 units received,5
`),

  h2('Sample JSON'),
  p('The same data as a JSON payload (array-under-`rows` form).'),
  code('json', `
{
  "rows": [
    { "invoice_id": "INV-2001", "vendor_name": "Workday", "invoice_amount": 27500, "po_number": "PO-8841", "exception_type": "Price Variance", "exception_description": "Invoice exceeds PO by 12% on three line items", "days_outstanding": 14 },
    { "invoice_id": "INV-2003", "vendor_name": "Acme Freight", "invoice_amount": 15200, "po_number": null, "exception_type": "Missing PO", "exception_description": "No purchase order referenced on the invoice", "days_outstanding": 21 },
    { "invoice_id": "INV-2006", "vendor_name": "Initech", "invoice_amount": 4200, "po_number": "PO-8852", "exception_type": "Duplicate", "exception_description": "Same invoice number and amount submitted six days ago", "days_outstanding": 6 }
  ]
}
`),

  h2('Sample exception record (after processing)'),
  p('What one invoice looks like once the pipeline has run (shape returned by `GET /v1/runs/{id}/results`):'),
  code('json', `
{
  "invoice_id": "INV-2001",
  "row": { "vendor_name": "Workday", "invoice_amount": "27500", "po_number": "PO-8841", "days_outstanding": 14 },
  "classification": {
    "primary_exception_type": "Price Variance",
    "severity": "HIGH",
    "severity_ai_suggested": "HIGH",
    "confidence_score": 0.92,
    "root_cause": "Unit price exceeds contract baseline on three lines.",
    "rationale": "Quantities and totals match the receipt; only unit price differs.",
    "model_id": "claude-...",
    "prompt_version": "classify.v1"
  },
  "resolution": {
    "resolution_path": "ESCALATE_CONTROLLER",
    "rule_id": "pv_escalate_controller_high",
    "rule_version": "2026.05.1",
    "requires_communication": true,
    "sla_hours": 8
  },
  "draft": {
    "channel": "finance_note",
    "subject": "Workday INV-2001 - 12% price variance for review",
    "template_id": "escalation_controller",
    "send_status": "draft"
  }
}
`),

  h2('Sample dashboard output'),
  p('What `GET /v1/runs/{id}/metrics` returns for the queue above:'),
  code('json', `
{
  "metrics": {
    "total_exceptions": 10,
    "auto_resolvable_count": 2,
    "escalations_required": 2,
    "total_exception_value": "182470",
    "sla_at_risk_count": 3,
    "average_confidence": 0.84,
    "breakdown_by_type": { "Price Variance": 4, "Quantity Mismatch": 2, "Missing PO": 1, "Duplicate": 1, "Unapproved Vendor": 1, "GRN Not Received": 1 },
    "breakdown_by_severity": { "HIGH": 3, "MEDIUM": 4, "LOW": 3 }
  },
  "priority_queues": {
    "high": [ { "invoice_id": "INV-2007", "priority_score": 0.81, "bucket": "HIGH", "drivers": ["amount", "unapproved_vendor"] } ],
    "medium": [],
    "low": []
  }
}
`),
];

export default blocks;
