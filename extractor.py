import os
import sys
import subprocess
import importlib

def auto_install_requirements():
    """Check for missing dependencies and auto-install from requirements.txt if needed."""
    try:
        import pypdfium2
        import pydantic
        import langchain_google_genai
        import dotenv
    except ImportError as e:
        print(f"Missing dependency detected: {e}. Auto-installing from requirements.txt...")
        script_dir = os.path.dirname(os.path.abspath(__file__))
        req_file = os.path.join(script_dir, "requirements.txt")
        if os.path.exists(req_file):
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_file])
                print("Dependencies successfully installed. Proceeding with execution...")
                importlib.invalidate_caches()
            except Exception as install_err:
                print(f"Failed to install dependencies: {install_err}")
        else:
            print(f"Cannot auto-install: requirements.txt not found at {req_file}")

auto_install_requirements()

import json
import glob
import requests
import pypdfium2 as pdfium
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv
# We will load the .env dynamically inside the function based on the provided path

class RawInvoiceExtraction(BaseModel):
    invoice_number: str = Field(description="The invoice number. Leave blank if not found.")
    invoice_amount: float = Field(description="The total invoice amount. Provide 0.0 if not found.")
    invoice_date: str = Field(description="The invoice date (e.g. YYYY-MM-DD). Leave blank if not found.")
    currency: str = Field(description="Currency code (e.g. USD). Leave blank if not found.")
    mos: str = Field(description="Month of Service (MOS). Leave blank if not found.")
    o_id: str = Field(description="Order ID (O-ID). Leave blank if not found.")
    p_id: str = Field(description="Purchase Order ID (P-ID). Leave blank if not found.")
    agency_name: str = Field(description="Agency Name. Leave blank if not found.")
    supplier_name: str = Field(description="Supplier/Vendor Name. Leave blank if not found.")
    client_name: str = Field(description="Client/Customer Name. Leave blank if not found.")
    payment_vendor: str = Field(description="Payment Vendor/Method (e.g., Wire, Check, Stripe). Leave blank if not found.")
    contains_invoice_word: bool = Field(description="True if the word 'Invoice' or 'INVOICE' explicitly appears anywhere in the document.")

def extract_invoice_data(pdf_path: str):
    """
    Extract data from PDF using Gemini Vision and enforce business rules.
    """
    try:
        import glob
        import os
        import traceback
        
        # If the path is relative, we assume UiPath passed it and it might be wrong. 
        # But if we instruct the user to pass Environment.CurrentDirectory, it will be absolute.
        if not os.path.isabs(pdf_path):
            raise Exception(f"Please pass an absolute path from UiPath. Received: {pdf_path}")
            
        # Dynamically find the project folder by going up two directories from data\Output
        # e.g., C:\...\Ap Exception Handling\data\Output -> C:\...\Ap Exception Handling
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(pdf_path)))
        load_dotenv(os.path.join(project_dir, ".env"))
        if os.path.isdir(pdf_path):
            files = []
            for ext in ("*.json", "*.csv", "*.pdf"):
                files.extend(glob.glob(os.path.join(pdf_path, ext)))
            if not files:
                raise Exception(f"Error: No supported files (.pdf, .csv, .json) found in directory: {pdf_path}")
            pdf_path = files[0]
            print(f"Directory detected. Automatically selected first file: {pdf_path}")

        file_ext = pdf_path.lower()
        if not (file_ext.endswith(".pdf") or file_ext.endswith(".csv") or file_ext.endswith(".json")):
            raise Exception(f"Error: Invalid file type. Expected .pdf, .csv, or .json, got: {pdf_path}")
            
        if not os.path.exists(pdf_path):
            raise Exception(f"Error: File not found: {pdf_path}")

        file_name = os.path.basename(pdf_path)

        # Handle JSON directly
        if file_ext.endswith(".json"):
            print(f"Extracting data directly from JSON file: {file_name}")
            with open(pdf_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    data = data[0]
                return {
                    "invoice_id": str(data.get("invoice_id", "")),
                    "vendor_name": str(data.get("vendor_name", "")),
                    "invoice_amount": float(data.get("invoice_amount", 0.0)),
                    "po_number": str(data.get("po_number", "")),
                    "exception_type": str(data.get("exception_type", "")),
                    "exception_description": str(data.get("exception_description", "")),
                    "days_outstanding": int(data.get("days_outstanding", 0)),
                    "approver_assigned": str(data.get("approver_assigned", ""))
                }

        # Handle CSV directly
        if file_ext.endswith(".csv"):
            import csv
            print(f"Extracting data directly from CSV file: {file_name}")
            with open(pdf_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                data = next(reader, {})
                return {
                    "invoice_id": str(data.get("invoice_id", data.get("Invoice ID", ""))),
                    "vendor_name": str(data.get("vendor_name", data.get("Vendor Name", ""))),
                    "invoice_amount": float(data.get("invoice_amount", data.get("Invoice Amount", 0.0))),
                    "po_number": str(data.get("po_number", data.get("PO Number", ""))),
                    "exception_type": str(data.get("exception_type", data.get("Exception Type", ""))),
                    "exception_description": str(data.get("exception_description", data.get("Exception Description", ""))),
                    "days_outstanding": int(data.get("days_outstanding", data.get("Days Outstanding", 0))),
                    "approver_assigned": str(data.get("approver_assigned", data.get("Approver Assigned", "")))
                }

        # 1. Convert PDF to Image(s) (existing logic)
        pdf = pdfium.PdfDocument(pdf_path)
        images = []
        for page_index in range(len(pdf)):
            page = pdf[page_index]
            # Render page to PIL image
            bitmap = page.render(scale=2.0)
            pil_image = bitmap.to_pil()
            images.append(pil_image)
            # We'll just use the first page for extraction to save tokens, 
            # but you can extend this to process all pages.
            break 

        # 2. Call Gemini Vision
        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
        structured_llm = llm.with_structured_output(RawInvoiceExtraction)
        
        import io
        import base64
        buffered = io.BytesIO()
        images[0].save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        img_data_uri = f"data:image/jpeg;base64,{img_str}"

        # We pass the image to the model using Langchain's multimodal HumanMessage
        prompt_text = "Extract the following invoice fields from this image. Ensure to follow the schema perfectly."
        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt_text},
                {"type": "image_url", "image_url": {"url": img_data_uri}}
            ]
        )
        
        print(f"Extracting data from {file_name} using Gemini Vision...")
        extraction: RawInvoiceExtraction = structured_llm.invoke([message])
        
        # 3. Apply Business Rules
        exception_type = ""
        exception_description = ""
        
        # Rule: Must contain "Invoice"
        if not extraction.contains_invoice_word:
            exception_type = "Other"
            exception_description = "Document does not contain the word 'Invoice'"
            
        # Rule: Amount cannot be negative
        elif extraction.invoice_amount < 0:
            exception_type = "Price Variance"
            exception_description = f"Invoice amount is negative: {extraction.invoice_amount}"
            
        else:
            # Rule: O-ID check
            is_o_id_valid = extraction.o_id.startswith("O-D")
            
            if not is_o_id_valid:
                # If O-ID is missing or invalid, check Important Fields
                important_fields = {
                    "Invoice number": extraction.invoice_number,
                    "Invoice Amount": str(extraction.invoice_amount) if extraction.invoice_amount > 0 else "",
                    "Invoice Date": extraction.invoice_date,
                    "MOS": extraction.mos,
                    "Agency name": extraction.agency_name,
                    "Supplier name": extraction.supplier_name,
                    "client name": extraction.client_name,
                    "payment vendor": extraction.payment_vendor
                }
                
                missing_fields = [k for k, v in important_fields.items() if not v or str(v).strip() == ""]
                
                if not extraction.p_id:
                    exception_type = "Missing PO"
                    exception_description = "P-ID (Purchase Order) is missing from the invoice."
                elif missing_fields:
                    exception_type = "Other"
                    exception_description = f"Missing mandatory important fields: {', '.join(missing_fields)}"

        # 4. Construct Final Payload
        payload = {
            "invoice_id": extraction.invoice_number,
            "vendor_name": extraction.supplier_name or extraction.agency_name,
            "invoice_amount": float(extraction.invoice_amount),
            "po_number": extraction.p_id,
            "exception_type": exception_type,
            "exception_description": exception_description,
            "days_outstanding": 0,
            "approver_assigned": ""
        }

        return payload
    except Exception as e:
        # Fallback to saving error log in the same dir as the script if possible, or project dir
        try:
            error_log_path = os.path.join(project_dir, "error_log.txt")
        except:
            error_log_path = r"C:\error_log_fallback.txt" # Absolute worst case fallback
            
        with open(error_log_path, "w") as f:
            import traceback
            f.write(traceback.format_exc())
        raise e

def extract_invoice_data_json(pdf_path: str):
    """
    Wrapper function for UiPath. Returns the payload as a JSON string
    which avoids Python-to-.NET object conversion errors.
    """
    import json
    import traceback
    try:
        payload = extract_invoice_data(pdf_path)
        return json.dumps(payload)
    except Exception as e:
        error_payload = {
            "error": str(e),
            "traceback": traceback.format_exc()
        }
        return json.dumps(error_payload)

def send_to_ap_agent(payload: dict):
    url = "http://127.0.0.1:8000/process-item"
    print(f"\nSending exception payload to AP Agent at {url}...")
    try:
        response = requests.post(url, json=payload)
        print("Response Status:", response.status_code)
        print(json.dumps(response.json(), indent=2))
    except Exception as e:
        print("Error connecting to AP Agent API:", e)

import glob

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Extract Invoice Data and handle exceptions.")
    parser.add_argument("--dir", default="Data/Output", help="Directory containing PDF invoices")
    args = parser.parse_args()
    
    data_dir = args.dir
    if not os.path.exists(data_dir):
        print(f"Error: Directory '{data_dir}' does not exist. Please create it and add PDFs.")
        exit(1)
        
    pdf_files = glob.glob(os.path.join(data_dir, "*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in '{data_dir}'.")
        exit(0)
        
    print(f"Found {len(pdf_files)} PDF(s) in '{data_dir}'. Processing...")
    
    for pdf_path in pdf_files:
        print(f"\n{'='*50}\nProcessing: {os.path.basename(pdf_path)}\n{'='*50}")
        try:
            result_payload = extract_invoice_data(pdf_path)
            print("\n--- Extracted Data & Exception Assessment ---")
            print(json.dumps(result_payload, indent=2))
            
            # If an exception was flagged by our rules, send to the AP Agent!
            if result_payload.get("exception_type"):
                print(f"\n[!] Exception Detected: {result_payload['exception_type']}")
                send_to_ap_agent(result_payload)
            else:
                print("\n[✓] No exceptions detected. Invoice data is clean and ready for Performer Queue!")
                
        except Exception as e:
            print(f"Error: Extraction failed for {pdf_path}: {e}")
