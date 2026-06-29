import sys
import os
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.exception_models import APException
from services.llm_service import LLMService
from services.classification_service import ClassificationService

def test():
    exc = APException(
        invoice_id="INV-9162",
        vendor_name="Unknown Vendor LLC",
        invoice_amount=4310.93,
        po_number="PO-81598",
        exception_type="Duplicate",
        exception_description="Potential duplicate billing for last month's services.",
        days_outstanding=17,
        approver_assigned="finance@company.com"
    )
    llm = LLMService()
    svc = ClassificationService(llm)
    try:
        res = svc.classify_exception(exc)
        print("Success:", res)
    except Exception as e:
        print("Error during classification:")
        traceback.print_exc()

if __name__ == "__main__":
    test()
