import sys
import os

sys.path.insert(0, '.')
os.environ.setdefault('PROJECT_ID', 'test-project')
os.environ.setdefault('LOCATION', 'us-central1')
os.environ.setdefault('DEMO_MODE', 'true')

from invoice_processing.core.exception_classifier import ExceptionClassifier, EXCEPTION_TYPES


def test_classify():
    classifier = ExceptionClassifier()
    exceptions = [
        {"invoice_id": "TEST-001", "vendor_name": "ABC Corp", "invoice_amount": "100", "po_number": "PO1"}
    ]
    res = classifier.classify_batch(exceptions, erp_context={}, master_rules={})

    # Must return exactly one result for one input invoice
    assert len(res) == 1, f"Expected 1 result, got {len(res)}"

    # Classified type must be one of the known canonical exception types
    assert res[0].primary_type in EXCEPTION_TYPES, (
        f"primary_type '{res[0].primary_type}' is not a valid exception type"
    )

    # invoice_id must be carried through correctly
    assert res[0].invoice_id == "TEST-001", (
        f"Expected invoice_id 'TEST-001', got '{res[0].invoice_id}'"
    )

    # Confidence must be a float between 0 and 1
    assert 0.0 <= res[0].confidence <= 1.0, (
        f"Confidence {res[0].confidence} out of range [0, 1]"
    )
