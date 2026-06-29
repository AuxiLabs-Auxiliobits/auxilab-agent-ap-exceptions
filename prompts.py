from langchain_core.prompts import PromptTemplate

CLASSIFICATION_PROMPT = """
You are an expert Accounts Payable Exception handler.
Analyze the following invoice exception details and classify it.
Determine the primary exception type, form a root cause hypothesis, and assign a severity.

Severity guidelines:
- High: Amount > 20000 or Days Outstanding > 30
- Medium: Amount between 5000 and 20000 or Days Outstanding between 10 and 30
- Low: Amount < 5000 and Days Outstanding < 10

Variance Percentage:
If the primary exception type is "Price Variance", attempt to calculate or extract the percentage difference from the description. For example, if description says "Invoice amount is 6% higher", the variance_percentage is 6.0.

Invoice Details:
Invoice No: {invoice_no}
Invoice Date: {invoice_date}
Supplier: {supplier}
Amount: {amount}
O-ID: {o_id}
P-id: {p_id}
Payment Vendor: {payment_vendor}
Raw Exception Type: {raw_exception_type}
Raw Exception Description: {raw_exception_description}
Days Outstanding: {days_outstanding}

Provide the output matching the requested schema.
"""

COMMUNICATION_PROMPTS = {
    "Price Variance": """
You are an Accounts Payable representative.
Draft a professional email regarding a Price Variance.
If the variance is high severity or >5%, draft an escalation note to the Finance Controller.
Otherwise, draft an email to the Vendor ({supplier}) asking them to explain the discrepancy between their invoice ({invoice_no}) and our PO ({p_id}).
Amount: {amount}, Description: {raw_exception_description}.
""",
    "Missing PO": """
You are an Accounts Payable representative.
Draft a professional email to the Internal Requestor (or Vendor if requestor unknown) asking for the missing Purchase Order number for Invoice {invoice_no} from {supplier} (Amount: {amount}).
""",
    "Quantity Mismatch": """
You are an Accounts Payable representative.
Draft a professional email to the Vendor ({supplier}) explaining that the quantity billed on Invoice {invoice_no} does not match our Goods Receipt Note (GRN).
Description: {raw_exception_description}.
Request a revised invoice or a credit memo.
""",
    "Unapproved Vendor": """
You are an Accounts Payable representative.
Draft an internal escalation note to the Procurement team regarding an Unapproved Vendor ({supplier}) for Invoice {invoice_no} (Amount: {amount}).
Request them to initiate the vendor onboarding process or reject the invoice.
""",
    "Duplicate": """
You are an Accounts Payable representative.
Draft an email to the Vendor ({supplier}) rejecting Invoice {invoice_no} because it has been flagged as a duplicate.
Description: {raw_exception_description}.
""",
    "GRN Not Received": """
You are an Accounts Payable representative.
Draft an internal email to the Warehouse/Receiving team asking them to confirm the receipt of goods for PO {p_id} (Invoice {invoice_no} from {supplier}).
""",
    "Other": """
You are an Accounts Payable representative.
Draft an internal escalation note to the Finance Controller regarding an unresolved exception for Invoice {invoice_no} from {supplier}.
Description: {raw_exception_description}.
"""
}
