"""
AP Exception Intelligence Dashboard - Flask Backend
Serves the standalone dashboard UI with live pipeline data.
"""

import csv
import json
import os
import shutil
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from werkzeug.utils import secure_filename

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)

# Resolve paths relative to this file
UI_DIR = Path(__file__).resolve().parent
PROJECT_DIR = UI_DIR.parent
EXCEPTION_OUTPUT_DIR = PROJECT_DIR / "invoice_processing" / "data" / "exception_output"
EXEMPLARY_QUEUE_DIR = PROJECT_DIR / "invoice_processing" / "exemplary_data" / "exception_queue"
EXEMPLARY_BASE_DIR = PROJECT_DIR / "invoice_processing" / "exemplary_data"
UPLOAD_STAGING_DIR = UI_DIR / "uploads"
UPLOAD_STAGING_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {"csv", "pdf", "png", "jpg", "jpeg", "gif", "webp", "json"}

# In-memory pipeline job tracker  {job_id: {status, message, output_path, error}}
_jobs: dict[str, dict] = {}


# ── Helpers ──────────────────────────────────────────────────────────────────

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_latest_run_dir() -> Path | None:
    """Return the most recent exception output run directory."""
    if not EXCEPTION_OUTPUT_DIR.exists():
        return None
    run_dirs = sorted(
        [d for d in EXCEPTION_OUTPUT_DIR.iterdir() if d.is_dir()],
        key=lambda d: d.name,
        reverse=True,
    )
    return run_dirs[0] if run_dirs else None


def load_json_file(path: Path) -> dict | list:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _format_run_ts(run_id: str) -> str:
    try:
        from datetime import timedelta
        dt = datetime.strptime(run_id, "%Y%m%d_%H%M%S")
        dt_ist = dt + timedelta(hours=5, minutes=30)
        return dt_ist.strftime("%b %d, %Y %H:%M:%S IST")
    except Exception:
        return run_id


def _run_pipeline_async(job_id: str, csv_path: Path) -> None:
    """Run the pipeline in a background thread and update _jobs."""
    _jobs[job_id]["status"] = "running"
    _jobs[job_id]["message"] = "Pipeline is processing…"
    try:
        venv_python = PROJECT_DIR / ".venv" / "Scripts" / "python.exe"
        python_exe = str(venv_python) if venv_python.exists() else sys.executable

        cli_script = PROJECT_DIR / "run_queue_cli.py"
        result = subprocess.run(
            [python_exe, str(cli_script), "--file", str(csv_path)],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_DIR),
            timeout=None,
        )
        if result.returncode == 0:
            run_dir = get_latest_run_dir()
            _jobs[job_id]["status"] = "done"
            _jobs[job_id]["message"] = "Pipeline completed successfully."
            _jobs[job_id]["output_path"] = run_dir.name if run_dir else ""
            _jobs[job_id]["stdout"] = result.stdout[-3000:] if result.stdout else ""
        else:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["message"] = result.stderr[-500:] or "Unknown error"
    except Exception as e:
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["message"] = str(e)


def _run_inference_async(job_id: str, case_id: str) -> None:
    """Run the single document inference pipeline in a background thread."""
    _jobs[job_id]["status"] = "running"
    _jobs[job_id]["message"] = "Inference pipeline is processing document..."
    try:
        venv_python = PROJECT_DIR / ".venv" / "Scripts" / "python.exe"
        python_exe = str(venv_python) if venv_python.exists() else sys.executable

        cli_script = PROJECT_DIR / "run_single_inference_cli.py"
        result = subprocess.run(
            [python_exe, str(cli_script), "--case", case_id],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_DIR),
            timeout=None,
        )
        if result.returncode == 0:
            _jobs[job_id]["status"] = "done"
            _jobs[job_id]["message"] = "Inference completed successfully."
            _jobs[job_id]["stdout"] = result.stdout  # Contains JSON
            _jobs[job_id]["stderr"] = result.stderr  # Contains logs
            try:
                stdout_str = result.stdout.strip()
                json_start = stdout_str.find('{')
                final_output = None
                if json_start != -1:
                    res_dict = json.loads(stdout_str[json_start:])
                    _jobs[job_id]["result"] = res_dict
                    
                    # Load the Postprocessing_Data.json if available
                    final_output = res_dict.get("final_output")
                if final_output:
                    pp_path = Path(final_output) / "Postprocessing_Data.json"
                    if pp_path.exists():
                        with open(pp_path, encoding="utf-8") as f:
                            pp = json.load(f)
                            _jobs[job_id]["postprocessing"] = pp
                            
                            # Auto-add to queue if rejected
                            status = pp.get("Invoice Processing", {}).get("Invoice Status", "Unknown")
                            is_rejected = status.lower() in ["rejected", "reject", "error"]
                            
                            if is_rejected:
                                import csv
                                queue_csv_path = EXEMPLARY_QUEUE_DIR / "exception_queue.csv"
                                
                                inv_id = case_id
                                vendor_name = pp.get("Vendor Information", {}).get("Vendor Name", "Unknown")
                                invoice_number = pp.get("Invoice Details", {}).get("Vendor Invoice", "Unknown")
                                invoice_amount = pp.get("Invoice Details", {}).get("Invoice Total", "0.00")
                                currency = pp.get("Invoice Details", {}).get("Currency", "USD")
                                po_number = pp.get("Invoice Details", {}).get("PO Number", "")
                                invoice_date = pp.get("Invoice Details", {}).get("Invoice Date", "2023-01-01")
                                
                                # Ensure trailing newline before append
                                if queue_csv_path.exists() and queue_csv_path.stat().st_size > 0:
                                    with open(queue_csv_path, "rb") as bf:
                                        bf.seek(-1, 2)
                                        if bf.read() != b'\n':
                                            with open(queue_csv_path, "a", encoding="utf-8") as af:
                                                af.write("\n")

                                # Append to CSV
                                with open(queue_csv_path, "a", newline="", encoding="utf-8") as csvfile:
                                    writer = csv.writer(csvfile)
                                    writer.writerow([inv_id, vendor_name, invoice_number, invoice_amount, currency, po_number, invoice_date])
                                
                                # Launch the exception queue pipeline in the background so it shows up natively
                                queue_job_id = job_id + "_queue"
                                _jobs[queue_job_id] = {
                                    "status": "starting",
                                    "type": "pipeline",
                                    "filename": "exception_queue.csv"
                                }
                                t = threading.Thread(
                                    target=_run_pipeline_async, args=(queue_job_id, queue_csv_path), daemon=True
                                )
                                t.start()
            except Exception as e:
                pass
        else:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["message"] = result.stderr[-500:] or "Unknown error during inference"
            _jobs[job_id]["stderr"] = result.stderr
            _jobs[job_id]["stdout"] = result.stdout
    except Exception as e:
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["message"] = str(e)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/dashboard")
def api_dashboard():
    """Return dashboard data from the latest run."""
    run_dir = get_latest_run_dir()
    if not run_dir:
        return jsonify({"error": "No pipeline output found. Please run the pipeline first."}), 404

    dashboard = load_json_file(run_dir / "dashboard.json")
    priority_queue = load_json_file(run_dir / "priority_queue.json")

    auto_resolved_items = []
    auto_resolved_csv_path = run_dir / "auto_resolved_queue.csv"
    if auto_resolved_csv_path.exists():
        with open(auto_resolved_csv_path, encoding="utf-8") as f:
            auto_resolved_items = list(csv.DictReader(f))

    valid_items = []
    valid_csv_path = run_dir / "valid_invoice_queue.csv"
    if valid_csv_path.exists():
        with open(valid_csv_path, encoding="utf-8") as f:
            valid_items = list(csv.DictReader(f))

    all_runs = sorted(
        [d for d in EXCEPTION_OUTPUT_DIR.iterdir() if d.is_dir()],
        key=lambda d: d.name,
        reverse=True,
    )[:10]

    run_history = []
    for r in all_runs:
        db_path = r / "dashboard.json"
        if db_path.exists():
            db = load_json_file(db_path)
            run_history.append({
                "run_id": r.name,
                "timestamp": _format_run_ts(r.name),
                "total_invoices": db.get("total_invoices", 0),
                "payments_blocked": db.get("payments_blocked", 0),
                "escalations_required": db.get("escalations_required", 0),
                "avg_score": db.get("average_normalized_priority_score", 0),
            })

    return jsonify({
        "run_id": run_dir.name,
        "timestamp": _format_run_ts(run_dir.name),
        "dashboard": dashboard,
        "priority_queue": priority_queue if isinstance(priority_queue, list) else [],
        "auto_resolved": auto_resolved_items,
        "valid_invoices": valid_items,
        "run_history": run_history,
    })


@app.route("/api/upload", methods=["POST"])
def api_upload():
    """
    Handle file upload.

    Accepts multipart/form-data with:
      - file: the uploaded file (CSV, PDF, image)
      - run_pipeline: "true" | "false"  (only for CSV)

    Returns JSON with:
      - success, filename, file_type, saved_path, job_id (if pipeline started)
    """
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file part in request."}), 400

    f = request.files["file"]
    if not f or f.filename == "":
        return jsonify({"success": False, "error": "No file selected."}), 400

    if not allowed_file(f.filename):
        return jsonify({
            "success": False,
            "error": f"File type not allowed. Accepted: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        }), 400

    filename = secure_filename(f.filename)
    ext = filename.rsplit(".", 1)[1].lower()

    # CSV → save directly to exception_queue directory (overwrites or adds)
    if ext == "csv":
        dest = EXEMPLARY_QUEUE_DIR / filename
        f.save(str(dest))
        run_pipeline = request.form.get("run_pipeline", "false").lower() == "true"
        job_id = None
        if run_pipeline:
            job_id = str(uuid.uuid4())[:8]
            _jobs[job_id] = {
                "type": "queue",
                "status": "queued",
                "message": "Queued for processing…",
                "filename": filename,
                "output_path": "",
                "stdout": "",
            }
            t = threading.Thread(
                target=_run_pipeline_async, args=(job_id, dest), daemon=True
            )
            t.start()

        return jsonify({
            "success": True,
            "filename": filename,
            "file_type": "csv",
            "saved_path": str(dest),
            "job_id": job_id,
            "message": f"Saved '{filename}' to exception queue folder."
            + (" Pipeline started." if run_pipeline else ""),
        })

    # PDF / Image → create a single case folder and run inference
    else:
        case_id = f"upload_{str(uuid.uuid4())[:8]}"
        dest_dir = EXEMPLARY_BASE_DIR / case_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename
        f.save(str(dest))
        file_type = "pdf" if ext == "pdf" else "image"
        
        run_pipeline = request.form.get("run_pipeline", "false").lower() == "true"
        job_id = None
        if run_pipeline:
            job_id = str(uuid.uuid4())[:8]
            _jobs[job_id] = {
                "type": "inference",
                "status": "queued",
                "message": "Queued for document inference…",
                "filename": filename,
                "output_path": "",
                "stdout": "",
            }
            t = threading.Thread(
                target=_run_inference_async, args=(job_id, case_id), daemon=True
            )
            t.start()

        return jsonify({
            "success": True,
            "filename": filename,
            "file_type": file_type,
            "saved_path": str(dest),
            "job_id": job_id,
            "message": f"'{filename}' saved to {case_id}."
            + (" Inference pipeline started." if run_pipeline else ""),
        })


@app.route("/api/jobs/<job_id>")
def api_job_status(job_id: str):
    """Poll the status of a pipeline job."""
    job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    return jsonify(job)


@app.route("/api/runs")
def api_runs():
    if not EXCEPTION_OUTPUT_DIR.exists():
        return jsonify([])
    runs = sorted(
        [d.name for d in EXCEPTION_OUTPUT_DIR.iterdir() if d.is_dir()],
        reverse=True,
    )
    return jsonify(runs)


@app.route("/api/runs/<run_id>")
def api_run_detail(run_id: str):
    run_dir = EXCEPTION_OUTPUT_DIR / run_id
    if not run_dir.exists():
        return jsonify({"error": "Run not found"}), 404

    dashboard = load_json_file(run_dir / "dashboard.json")
    priority_queue = load_json_file(run_dir / "priority_queue.json")

    return jsonify({
        "run_id": run_id,
        "timestamp": _format_run_ts(run_id),
        "dashboard": dashboard,
        "priority_queue": priority_queue if isinstance(priority_queue, list) else [],
    })


if __name__ == "__main__":
    import logging
    import flask.cli
    flask.cli.show_server_banner = lambda *args, **kwargs: None
    class NoDevServerWarningFilter(logging.Filter):
        def filter(self, record):
            return "development server" not in record.getMessage().lower()
    logging.getLogger("werkzeug").addFilter(NoDevServerWarningFilter())

    print("=" * 60)
    print("  AP Exception Intelligence Dashboard")
    print("  Running at: http://localhost:5001")
    print("=" * 60)
    app.run(debug=False, port=5001, host="0.0.0.0")
