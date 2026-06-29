from typing import Tuple

def assign_resolution_path(exception_type: str, severity: str, amount: float, variance_percentage: float = None) -> Tuple[str, bool]:
    """
    Deterministic rules engine to assign a resolution path based on exception details.
    Returns a tuple of (resolution_path, requires_communication).
    """
    if exception_type == "Price Variance":
        var_pct = variance_percentage if variance_percentage is not None else 0.0
        
        if var_pct < 2.0:
            return "Auto-approve with note (Minor Variance)", False
        elif var_pct > 5.0 or severity == "High":
            return "Escalate to Finance Controller", True
        else:
            return "Request explanation from Vendor", True
            
    elif exception_type == "Missing PO":
        return "Request PO from Internal Requestor", True
        
    elif exception_type == "Quantity Mismatch":
        return "Request credit memo/revised invoice from Vendor", True
        
    elif exception_type == "Unapproved Vendor":
        return "Hold pending Procurement review & onboarding", True
        
    elif exception_type == "Duplicate":
        return "Reject invoice and notify Vendor", True
        
    elif exception_type == "GRN Not Received":
        return "Hold pending Warehouse GRN confirmation", True
        
    else:
        return "Manual review required", False
