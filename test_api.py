import requests
import json

url = "http://127.0.0.1:8000/process_exception"
payload = {
    "invoice_no": "INV-1029",
    "amount": 45000,
    "supplier": "SAP",
    "payment_vendor": "Wire Transfer",
    "exception_type": "Price Variance",
    "exception_description": "Invoice amount is 6% higher than PO amount",
    "days_outstanding": 12
}

try:
    response = requests.post(url, json=payload)
    print("Status Code:", response.status_code)
    print("Response JSON:")
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print("Error:", e)
