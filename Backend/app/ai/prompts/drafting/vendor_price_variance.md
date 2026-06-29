Channel: vendor_email
Template ID: vendor_price_variance.v1

Write a vendor-facing email regarding a price variance between the submitted
invoice and the corresponding purchase order. Request that the vendor either
(a) issue a corrected invoice matching the PO price, or (b) provide written
justification (signed amendment, rate-card change notice) for the variance.

Include a clear deadline derived from {{sla_hours}}. Reference {{invoice_id}}
and {{po_number}} and the {{variance_pct}} figure if present.
