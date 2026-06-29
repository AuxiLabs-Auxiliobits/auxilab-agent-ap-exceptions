import { h1, h2, h3, p, table, code, note, hr, type Block } from '../blocks';

const blocks: Block[] = [
  h1('File Import (CSV & JSON)'),
  p('You feed the agent an **exception queue** — a list of invoice exceptions exported from your ERP. This page is the contract for that file.'),
  note('The console **Download CSV template** and **Accepted format** helper are generated from the same source as this page. For the live, authoritative schema call `GET /v1/upload/format`.'),

  h2('Accepted formats'),
  table(
    ['Property', 'Value'],
    [
      ['**File types**', '`.csv`, `.json`'],
      ['**Max size**', '**25 MB** per upload (larger files are rejected with `413`)'],
      ['**Encoding**', 'UTF-8 (a UTF-8 BOM is tolerated)'],
      ['**CSV delimiter**', 'Comma; the header row is required'],
      ['**JSON shape**', 'An array of objects, or `{ "rows": [ … ] }`'],
    ],
  ),

  h2('Required columns'),
  table(
    ['Column', 'Type', 'Notes'],
    [
      ['`invoice_id`', 'string', 'Unique within the file. 1–64 chars.'],
      ['`vendor_name`', 'string', '1–256 chars.'],
      ['`invoice_amount`', 'number', '`≥ 0`. Currency symbols/commas are stripped.'],
      ['`exception_type`', 'string', 'The ERP-declared type (the AI may re-classify).'],
      ['`exception_description`', 'string', 'Free text, 1–2000 chars — the AI reads this.'],
      ['`days_outstanding`', 'integer', '`≥ 0`. Age of the exception in days.'],
    ],
  ),
  h3('Optional columns'),
  table(
    ['Column', 'Type', 'Notes'],
    [
      ['`po_number`', 'string', 'Purchase-order reference, if any.'],
      ['`approver_assigned`', 'string', 'Pre-assigned approver, if any.'],
    ],
  ),

  h2('Alias detection (column mapping)'),
  p('Headers do not have to match exactly. Common variants are mapped automatically — for example:'),
  table(
    ['Canonical', 'Accepted aliases (examples)'],
    [
      ['`invoice_id`', '`invoice`, `invoice_no`, `invoice number`, `inv_id`'],
      ['`vendor_name`', '`vendor`, `supplier`, `supplier_name`, `payee`'],
      ['`invoice_amount`', '`amount`, `total`, `invoice_total`, `gross_amount`'],
      ['`exception_type`', '`type`, `exception`, `category`'],
      ['`exception_description`', '`description`, `notes`, `reason`, `details`'],
      ['`days_outstanding`', '`age`, `days`, `dso`, `days_open`'],
      ['`po_number`', '`po`, `po_no`, `purchase_order`'],
    ],
  ),
  p('Matching is case-insensitive and ignores spacing/underscores. If a required column cannot be matched to any alias, the **whole upload is rejected** with a clear message naming the missing column.'),

  h2('Validation rules'),
  p('Each row is validated independently. A row that fails is **quarantined** (not silently dropped); the rest of the file still processes.'),
  table(
    ['Rule', 'Failure → reason code'],
    [
      ['Required column present & non-empty', '`MISSING_FIELD`'],
      ['`invoice_amount` parses to a number `≥ 0`', '`INVALID_AMOUNT`'],
      ['`days_outstanding` parses to an integer `≥ 0`', '`INVALID_DAYS`'],
      ['`invoice_date` (if present) not in the future', '`FUTURE_DATE`'],
      ['`invoice_id` within length limits', '`INVALID_ID`'],
      ['Spreadsheet-formula prefixes neutralized', 'sanitized, not rejected'],
    ],
  ),
  note('**CSV-injection safety:** cells beginning with `=`, `+`, `-`, or `@` are neutralized so a malicious export cannot execute a formula if the file is later opened in a spreadsheet.'),

  h2('Error handling & rejection reports'),
  p('Rows that fail validation appear in the **Queue → Quarantined** panel with their row index, the raw values, and the reason. Download a **rejection report** (`GET /v1/runs/{id}/rejections.csv`) listing every rejected row and why — fix and re-upload just those. A completely unparseable file fails the whole run with status `FAILED` and a message.'),

  hr(),

  h2('Examples'),
  h3('CSV'),
  code('csv', `
invoice_id,vendor_name,invoice_amount,po_number,exception_type,exception_description,days_outstanding
INV-2001,Workday,27500,PO-8841,Price Variance,Invoice exceeds PO by 12% on 3 line items,14
INV-2002,Oracle,4800,PO-8842,Price Variance,Unit price 1.2% above contract baseline,3
INV-2003,Acme Freight,15200,,Missing PO,No purchase order referenced,21
`),
  h3('JSON'),
  code('json', `
{
  "rows": [
    {
      "invoice_id": "INV-2001",
      "vendor_name": "Workday",
      "invoice_amount": 27500,
      "po_number": "PO-8841",
      "exception_type": "Price Variance",
      "exception_description": "Invoice exceeds PO by 12% on 3 line items",
      "days_outstanding": 14
    }
  ]
}
`),
  p('See [Sample Data](/docs/sample-data) for a full, copy-paste-ready file.'),
];

export default blocks;
