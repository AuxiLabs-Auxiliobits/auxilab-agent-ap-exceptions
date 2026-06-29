import sys
import os

sys.path.insert(0, '.')
os.environ.setdefault('PROJECT_ID', 'project-b9c31b73-1c01-4c8a-b55')
os.environ.setdefault('LOCATION', 'us-central1')

from invoice_processing.core.exception_classifier import ExceptionClassifier

def run_test():
    print("Initializing classifier...")
    classifier = ExceptionClassifier()
    exceptions = [
        {"invoice_id": "TEST", "vendor_name": "ABC", "invoice_amount": "100", "po_number": "PO1"}
    ]
    print("Classifying...")
    res = classifier.classify_batch(exceptions, erp_context={}, master_rules={})
    print(f"Result: {res[0].primary_type}")

if __name__ == '__main__':
    run_test()
