import sys, os
sys.path.insert(0, '.')
os.environ.setdefault('PROJECT_ID', 'test-project')
os.environ.setdefault('LOCATION', 'us-central1')

print('--- Testing ResolutionRouter with InvoiceResult ---')
from invoice_processing.core.resolution_router import ResolutionRouter
from invoice_processing.core.exception_classifier import ExceptionClassification

router = ResolutionRouter()

# Mandatory Multi-Exception Test Case
raw_exceptions = [
    {
        'invoice_id': 'HP-99001',
        'vendor_name': 'HP Enterprise',
        'invoice_number': 'INV-99001',
        'invoice_amount': '15000',
        'days_outstanding': '15',
        'currency': 'EUR',
        'po_number': 'PO-99999',
    }
]

classifications = [
    ExceptionClassification(
        invoice_id='HP-99001',
        primary_type='Duplicate Invoice',
        evidence_used='Invoice history shows exact match',
        success=True
    ),
    ExceptionClassification(
        invoice_id='HP-99001',
        primary_type='PO Not Found',
        evidence_used='PO-99999 missing in ERP',
        success=True
    ),
    ExceptionClassification(
        invoice_id='HP-99001',
        primary_type='Currency Mismatch',
        evidence_used='Invoice in EUR, expected USD',
        success=True
    ),
]

invoices = router.assign_batch(raw_exceptions, classifications)

print(f"\nDiscovered {len(invoices)} invoices.")
hp_invoice = invoices[0]

print(f"\nInvoice: {hp_invoice.invoice_id} | Amount: ${hp_invoice.invoice_amount}")
print(f"Exceptions Discovered: {len(hp_invoice.exceptions)}")
for exc in hp_invoice.exceptions:
    print(f" - {exc.primary_type} (Confidence: {exc.confidence})")

print(f"\nPayment Blocked: {hp_invoice.payment_blocked}")
print(f"Escalation Required: {hp_invoice.escalation_required}")
print(f"Priority Score: {hp_invoice.priority_score}")
print(f"Root Cause Categories: {hp_invoice.root_cause_categories}")
print(f"Resolution Owners: {hp_invoice.resolution_owners}")
print(f"SLA Hours: {hp_invoice.sla_hours}")

print("\nDecision Trace:")
for trace in hp_invoice.decision_trace:
    print(f" * {trace}")

assert hp_invoice.payment_blocked == True, "Payment should be blocked"
assert hp_invoice.escalation_required == True, "Escalation should be required"
assert len(hp_invoice.exceptions) == 3, "Should have 3 exceptions"
assert "Duplicate Invoice" in [e.primary_type for e in hp_invoice.exceptions]
assert "PO Not Found" in [e.primary_type for e in hp_invoice.exceptions]
assert "Currency Mismatch" in [e.primary_type for e in hp_invoice.exceptions]

print("\nAssertions: ALL PASSED")

# Test QueueFormatter with InvoiceResult
print('\n--- Testing QueueFormatter with InvoiceResult ---')
from invoice_processing.core.queue_formatter import QueueFormatter

fmt = QueueFormatter()
output = fmt.build([hp_invoice])

assert output['total_invoices_in_exception'] == 1
assert 'dashboard' in output
assert 'priority_queue' in output
assert output['dashboard']['total_invoices'] == 1
assert output['dashboard']['payments_blocked'] == 1
assert output['dashboard']['escalations_required'] == 1
assert output['dashboard']['multi_exception_invoice_count'] == 1
print(f"  priority_queue length: {len(output['priority_queue'])}")
print(f"  dashboard: {output['dashboard']}")
print(f"  output_path: {output['output_path']}")
print("  QueueFormatter: PASSED")

print("\n" + "=" * 50)
print("ALL LOCAL TESTS PASSED")
print("=" * 50)
