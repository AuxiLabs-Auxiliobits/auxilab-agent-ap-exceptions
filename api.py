"""FastAPI REST API for AP Exception Handling Agent.

Provides enterprise API endpoints for programmatic access
to the AP exception handling workflow.
"""

import os
import sys
import shutil
from typing import Optional, Dict, Any
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config.logging_config import setup_logging
from config.settings import settings
from graph.workflow import run_workflow

logger = setup_logging("api")

app = FastAPI(
    title="AP Exception Handling Agent API",
    description="Enterprise AI-powered AP exception triage and resolution system",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# In-memory store for latest workflow results
_latest_results: dict = {}


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload an AP exception queue file (CSV or JSON).

    Accepts a CSV or JSON file, validates the extension, and saves it
    to the local data/ directory for subsequent processing.

    Args:
        file: Uploaded file.

    Returns:
        JSON with upload status, file path, and filename.

    Raises:
        HTTPException: If the file format is not accepted.
    """
    allowed_exts = (".csv", ".json")
    if not file.filename.lower().endswith(allowed_exts):
        raise HTTPException(400, "Only CSV and JSON (.json) files are accepted")

    os.makedirs("data", exist_ok=True)
    file_path = os.path.join("data", file.filename)

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    logger.info(f"File uploaded: {file_path}")
    return {"status": "success", "file_path": file_path, "filename": file.filename}


@app.post("/run-agent")
async def run_agent(csv_path: Optional[str] = "data/sample_queue.csv"):
    """Execute the full AP exception handling workflow.

    Runs the complete LangGraph pipeline on the specified CSV file
    and stores the results in memory for subsequent retrieval.

    Args:
        csv_path: Path to the CSV file to process.

    Returns:
        JSON with processing status, exception count, errors, and summary.

    Raises:
        HTTPException: If the workflow execution fails.
    """
    global _latest_results
    try:
        logger.info(f"Running agent workflow on: {csv_path}")
        result = run_workflow(csv_path)
        _latest_results = result
        return {
            "status": "success",
            "exceptions_processed": len(result.get("prioritized_queue", [])),
            "errors": result.get("errors", []),
            "summary": result.get("dashboard_summary", {}),
        }
    except Exception as e:
        logger.error(f"Agent workflow failed: {str(e)}")
        raise HTTPException(500, f"Workflow failed: {str(e)}")


@app.post("/process-item")
async def process_single_item(item: Dict[str, Any] = Body(...)):
    """Process a single AP exception item (e.g., from a UiPath Queue).

    Accepts a JSON payload representing a single exception, saves it
    to a temporary file, and runs the LangGraph pipeline on it.
    """
    global _latest_results
    try:
        os.makedirs("data", exist_ok=True)
        temp_path = os.path.join("data", "temp_queue_item.json")
        
        # Write the single item as a list to a temporary JSON file
        with open(temp_path, "w") as f:
            json.dump([item], f)
            
        logger.info(f"Running agent workflow on single item: {item.get('invoice_id', 'unknown')}")
        result = run_workflow(temp_path)
        _latest_results = result
        
        # Return the resolved exception and communication if available
        prioritized = result.get("prioritized_queue", [])
        communications = result.get("drafted_communications", [])
        comm = communications[0] if communications else None
        
        if prioritized:
            return {
                "status": "success", 
                "processed_item": prioritized[0],
                "communication": comm
            }
        else:
            return {"status": "success", "processed_item": None, "communication": None, "errors": result.get("errors", [])}
            
    except Exception as e:
        logger.error(f"Single item workflow failed: {str(e)}")
        raise HTTPException(500, f"Workflow failed: {str(e)}")


@app.get("/summary")
async def get_summary():
    """Get the dashboard summary from the latest workflow run.

    Returns:
        JSON with dashboard summary statistics.

    Raises:
        HTTPException: If no workflow results are available.
    """
    if not _latest_results:
        raise HTTPException(404, "No workflow results available. Run the agent first.")
    return _latest_results.get("dashboard_summary", {})


@app.get("/exceptions")
async def get_exceptions():
    """Get all classified exceptions from the latest workflow run.

    Returns:
        JSON list of classified exception records.

    Raises:
        HTTPException: If no workflow results are available.
    """
    if not _latest_results:
        raise HTTPException(404, "No workflow results available. Run the agent first.")
    return _latest_results.get("classified_queue", [])


@app.get("/communications")
async def get_communications():
    """Get all drafted communications from the latest workflow run.

    Returns:
        JSON list of drafted communication records.

    Raises:
        HTTPException: If no workflow results are available.
    """
    if not _latest_results:
        raise HTTPException(404, "No workflow results available. Run the agent first.")
    return _latest_results.get("drafted_communications", [])


class EmailRequest(BaseModel):
    to_email: str
    subject: str
    body: str

@app.post("/send-email")
async def send_email_gmail(request: EmailRequest):
    """Send an email using Gmail SMTP.

    This endpoint can be called from UiPath via an HTTP Request activity.
    Requires GMAIL_ADDRESS and GMAIL_APP_PASSWORD to be set in .env.
    """
    if not settings.GMAIL_ADDRESS or not settings.GMAIL_APP_PASSWORD:
        raise HTTPException(500, "Gmail credentials not configured in settings (.env)")
        
    try:
        import markdown
        import urllib.parse
        
        # Parse the markdown body with extensions to make it more robust
        md_html = markdown.markdown(request.body, extensions=['sane_lists', 'nl2br'])
        subject_urlencoded = urllib.parse.quote(request.subject)
        
        # Build the HTML template
        html_content = f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background-color: #f4f7f6;
                    margin: 0;
                    padding: 20px;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background-color: #ffffff;
                    border-radius: 8px;
                    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                    overflow: hidden;
                    border-top: 4px solid #0056b3;
                }}
                .header {{
                    background-color: #0056b3;
                    color: #ffffff;
                    padding: 20px;
                    text-align: center;
                }}
                .header h2 {{
                    margin: 0;
                    font-size: 24px;
                }}
                .content {{
                    padding: 30px;
                    color: #333333;
                    line-height: 1.6;
                }}
                .content h1, .content h2, .content h3 {{
                    color: #0056b3;
                }}
                .button-container {{
                    text-align: center;
                    margin-top: 30px;
                }}
                .button {{
                    display: inline-block;
                    background-color: #28a745;
                    color: white;
                    padding: 12px 24px;
                    text-decoration: none;
                    border-radius: 4px;
                    font-weight: bold;
                    font-size: 16px;
                }}
                .footer {{
                    background-color: #f8f9fa;
                    color: #6c757d;
                    text-align: center;
                    padding: 15px;
                    font-size: 12px;
                    border-top: 1px solid #e9ecef;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>AP Exception Alert</h2>
                </div>
                <div class="content">
                    {md_html}
                    
                    <div class="button-container">
                        <a href="mailto:ap-support@auxiliobits.com?subject=Re: {subject_urlencoded}" class="button">Reply to Resolve Exception</a>
                    </div>
                </div>
                <div class="footer">
                    &copy; 2026 AP Exception Handling System. This is an automated message.
                </div>
            </div>
        </body>
        </html>
        """
        
        msg = MIMEMultipart('alternative')
        msg['From'] = settings.GMAIL_ADDRESS
        
        # FOR TESTING PURPOSES: Override the recipient
        request.to_email = "manpreet.singh@auxiliobits.com"
        
        msg['To'] = request.to_email
        msg['Subject'] = request.subject
        
        # Attach both plain text and HTML versions
        msg.attach(MIMEText(request.body, 'plain'))
        msg.attach(MIMEText(html_content, 'html'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(settings.GMAIL_ADDRESS, settings.GMAIL_APP_PASSWORD)
        server.send_message(msg)
        server.quit()
        
        return {"status": "success", "message": f"Email sent successfully to {request.to_email}"}
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}")
        raise HTTPException(500, f"Failed to send email: {str(e)}")


@app.get("/health")
async def health_check():
    """Health check endpoint.

    Returns:
        JSON with service health status.
    """
    return {"status": "healthy", "service": "AP Exception Handling Agent"}
