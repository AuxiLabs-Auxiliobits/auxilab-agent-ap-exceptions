from pydantic import BaseModel, Field
from typing import Literal, Optional

class ExceptionClassification(BaseModel):
    primary_exception_type: Literal[
        "Price Variance", 
        "Missing PO", 
        "Quantity Mismatch", 
        "Unapproved Vendor", 
        "Duplicate", 
        "GRN Not Received", 
        "Other"
    ] = Field(description="The primary classification of the exception.")
    
    root_cause_hypothesis: str = Field(
        description="A brief hypothesis explaining the root cause of the exception based on the provided details."
    )
    
    severity: Literal["High", "Medium", "Low"] = Field(
        description="Severity based on amount and days outstanding."
    )
    
    variance_percentage: Optional[float] = Field(
        default=None, 
        description="If the exception is a Price Variance, extract or calculate the percentage variance (e.g., 6.5). Otherwise, leave null."
    )

class DraftCommunication(BaseModel):
    recipient_type: Literal["Vendor", "Internal Requestor", "Finance Controller", "Procurement", "Warehouse"] = Field(
        description="Who the communication is directed to."
    )
    subject: str = Field(description="Email/Message subject.")
    body: str = Field(description="The drafted email or message body addressing the exception.")

class InvoicePayload(BaseModel):
    invoice_no: str
    invoice_date: str = ""
    supplier: str = ""
    client: str = ""
    amount: float = 0.0
    O_ID: str = ""
    P_id: str = ""
    payment_vendor: str = ""
    exception_type: str = ""
    exception_description: str = ""
    days_outstanding: int = 0
    approver_assigned: str = ""
