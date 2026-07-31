import sys
import os

sys.path.insert(0, '.')
os.environ.setdefault('PROJECT_ID', 'test-project')
os.environ.setdefault('LOCATION', 'us-central1')

from invoice_processing.core.schema_mapper import SchemaMapper

def test_schema_mapper():
    mapper = SchemaMapper()
    raw_headers = [
        "InvoiceID", 
        "VendorName", 
        "InvoiceNumber", 
        "InvoiceDate", 
        "PONumber", 
        "InvoiceAmount", 
        "TaxAmount", 
        "Currency"
    ]
    
    mapping = mapper.map_headers(raw_headers)
    
    print(f"Generated Mapping: {mapping}")
    
    expected = {
        "InvoiceID": "invoice_id",
        "InvoiceNumber": "invoice_number",
        "InvoiceDate": "invoice_date",
        "VendorName": "vendor_name",
        "PONumber": "po_number",
        "InvoiceAmount": "invoice_amount",
        "TaxAmount": "tax_amount",
        "Currency": "currency"
    }
    
    for k, v in expected.items():
        assert mapping.get(k) == v, f"Expected {k} to map to {v}, but got {mapping.get(k)}"
        
    print("test_schema_mapper PASSED!")

