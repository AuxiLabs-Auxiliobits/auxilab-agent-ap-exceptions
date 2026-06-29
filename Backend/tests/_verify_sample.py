"""Read-only verification of the sample CSV against the brief."""
from decimal import Decimal

import pandas as pd

from app.schemas import ExceptionRow

df = pd.read_csv("sample_data/exception_queue.csv")
print(f"rows: {len(df)}")
print()
print("distribution:")
print(df["exception_type"].value_counts().to_string())
print()
print(f"amount range: ${df['invoice_amount'].min():.0f} - ${df['invoice_amount'].max():.0f}")
print(f"days range: {df['days_outstanding'].min()} - {df['days_outstanding'].max()}")

missing_po_blank = df["po_number"].isna().sum()
missing_po_type = (df["exception_type"] == "Missing PO").sum()
print(
    f"empty po_number: {missing_po_blank} "
    f"(expected {missing_po_type}, matches: {missing_po_blank == missing_po_type})"
)

# Vendor count
unique_vendors = df["vendor_name"].nunique()
max_invoices_per_vendor = df["vendor_name"].value_counts().max()
print(f"unique vendors: {unique_vendors}; max invoices/vendor: {max_invoices_per_vendor}")

print()
errors = 0
for i, r in enumerate(df.to_dict("records")):
    rec = {**r}
    rec["invoice_amount"] = Decimal(str(rec["invoice_amount"]))
    rec["po_number"] = rec["po_number"] if pd.notna(rec["po_number"]) else None
    rec["approver_assigned"] = rec["approver_assigned"] if pd.notna(rec["approver_assigned"]) else None
    try:
        ExceptionRow.model_validate(rec)
    except Exception as e:
        errors += 1
        print(f"row {i} ({rec.get('invoice_id')}): {e}")
print(f"schema validation: {len(df) - errors}/{len(df)} pass")
