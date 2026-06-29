# AP Invoice Exception Handling

A comprehensive, unified ADK-based solution for end-to-end Accounts Payable (AP) invoice processing and automated exception management. 

This project combines an intelligent document processing agent (with interactive learning) and a powerful batch exception queue pipeline to automate triage, classification, and resolution of AP exceptions.

---

## 1. Overview & Components

The system is composed of two primary sub-systems working in tandem:

### A. Invoice Processing Agent
A self-contained ADK agent that processes raw invoice documents (PDFs) through an inference pipeline and provides an interactive learning system for continuous improvement.
- **Interaction Type**: Conversational (Dual-mode: Inference and Learning)
- **Model**: `gemini-2.5-flash` for agent, `gemini-2.5-pro` for rule validation
- **Framework**: Google Agent Development Kit (ADK)
- **Key Capability**: 9-Agent Acting Pipeline (Classification, Extraction, Validation) paired with an Adaptive Learning Framework (ALF) to self-correct based on human feedback.

### B. Exception Queue Pipeline
A robust batch-processing CLI tool that ingests failed invoices or exceptions, classifies them using LLMs, routes them deterministically, and generates a prioritized work queue.
- **Interaction Type**: CLI / Batch Process (`run_queue_cli.py`)
- **Model**: `gemini-2.5-pro`
- **Key Capability**: Intelligent triage, evidence-based classification against ERP data, and automated communication drafting.

---

## 2. Architecture & Design Principles

### Design Principles
- **Black Box Acting Agent**: The core extraction and validation agents are never modified directly; all evolution happens downstream via the Adaptive Learning Framework (ALF).
- **Evidence-Based Reasoning**: The Exception Queue grounds all its LLM classifications strictly against mock ERP Database records (POs, GRNs, Vendor Master) to eliminate hallucinations.
- **Layered Corrections**: Deterministic rules execute first. LLMs are invoked only when needed for complex rule discovery or unstructured communication drafting.
- **Human Governance**: Every new exception correction rule requires Subject Matter Expert (SME) review and approval before being written to the rule base.
- **Configuration Over Code**: Domain knowledge lives in `master_data.yaml` to allow adapting to any document type.

### Three-Zone Architecture
1. **The Constitution Architecture:** The Reconstructed Rules Book serves as the agent's "constitution" -- the single source of truth and transparency governing decisions.
2. **The Runtime Inference Pipeline:** Input invoices flow through three sequential stages: Acting Agent (4-step internal pipeline), Critic Agent (Investigation audit), and ALF Engine (checks Rule Base and applies corrections).
3. **The Learning & Evolution Loop:** SMEs flag errors and provide feedback to the Rule Learning Agent (RLA). The RLA generates new exception rules into the ALF Rule Base for future runs. Periodic System Reviews promote these into permanent Acting Agent changes.

---

## 3. The Exception Queue Pipeline

The Exception Queue automates the manual triage AP clerks normally perform. It runs a 5-step pipeline:

1. **Ingest & Map**: Loads the exception queue (CSV/JSON), parses the schema, and cross-references data against the simulated ERP Database (`erp_database.json`).
2. **Classify (LLM)**: Utilizes Gemini (`gemini-2.5-pro`) to classify each exception into canonical categories using strict evidence-based reasoning:
   - *Amount Exceeds Tolerance, Exact/Potential Duplicate, PO Not Found, GRN Not Received, Vendor/Currency Mismatch, Missing Required Data, Future Date, VALID, Unknown, Other*.
   - Outputs structured schema including: `primary_type`, `root_cause_hypothesis`, `evidence_used`, `missing_data`, `confidence`, and `recommended_action`.
3. **Route (Deterministic)**: Evaluates classifications to determine a priority score, SLA, and whether the exception can be auto-resolved, requires escalation, or is blocked for payment.
4. **Draft Communications (LLM)**: For exceptions requiring vendor or internal contact, automatically drafts contextual emails based on extracted evidence.
5. **Output**: Compiles a prioritized queue (High, Medium, Low severity) and a comprehensive dashboard detailing business value metrics (Valid Value, Blocked Value, Duplicate Risk Value).

**Running the Queue:**
```bash
# Run the pipeline against a queue file
python run_queue_cli.py --file exception_queue/exception_queue.csv

# Run with debug tracing enabled
python run_queue_cli.py --file exception_queue/exception_queue.csv --debug
```

---

## 4. The Invoice Processing Agent (Inference & Learning)

The primary document processing agent operates in two selectable modes:

### Inference Mode
Runs the inference pipeline consisting of three stages:
1. **Acting Agent**: A 9-agent pipeline that classifies, extracts, and validates the invoice in 4 phases (Intake, PO/Invoice match, Status/Date, Totals/EWAF).
2. **Critic/Investigation (Optional)**: A 3-layer audit system that checks the Acting Agent's output against the reconstructed "rules book" (constitution).
3. **Adaptive Learning Framework (ALF)**: A Collect-Plan-Execute engine that evaluates active correction rules and patches fields deterministically to resolve known exceptions without modifying code.

### Learning Mode
Empowers SMEs to review processed cases and teach the agent new rules:
- SMEs identify a policy exception (e.g., "Emergency maintenance under $2000 does not need a WAF").
- The **Rule Learning Agent (RLA)** generates a deterministic rule via `discover_safe_rule`.
- The system automatically assesses the impact of the proposed rule against all historical cases to ensure no collateral damage.
- Once approved, the rule is saved to `rule_base.json` and immediately applies to future inference runs.

**Running the Agent:**
```bash
# Launch the ADK web UI
adk web invoice_processing

# Or use the non-interactive CLI mode
adk run invoice_processing
```

---

## 5. The Web UI Dashboard

To make the system accessible to business users (like AP Clerks), a full-stack Web Dashboard is included. It provides a beautiful, modern interface to interact with the underlying Agentic Pipeline.

### Key Features
- **Drag-and-Drop Document Upload**: Upload raw PDF or Image invoices directly. The backend automatically hands them to Gemini 2.5 Pro for OCR and schema extraction.
- **Live Status Polling**: Real-time feedback as the inference pipeline extracts data, validates against the ERP, and determines if the invoice is valid or rejected.
- **Automated Queue Integration**: If an invoice fails validation (e.g., Missing PO, Future Date), it is automatically appended to the `exception_queue.csv` and the background Exception Queue Pipeline is triggered.
- **Priority Queue View**: A sortable, filterable dashboard displaying the evaluated queue. It prominently features actual Invoice Numbers, calculated Priority Scores, dynamic SLAs, and flagged exceptions.

**Running the Dashboard:**
```bash
# Start the Flask web server
python ui/app.py
```
Then open `http://127.0.0.1:5001` in your browser.

---

## 6. Folder Structure

```text
APInvoiceExceptionHandling/
└── python/
    └── agents/
        └── invoice-processing/
            ├── invoice_processing/              
            │   ├── agent.py                    # Dual-mode LlmAgent & run_exception_queue pipeline
            │   ├── core/                       # Learning logic, ML orchestration, Config, Rule handling
            │   │   ├── exception_classifier.py # Gemini Exception Classifier
            │   │   ├── rule_discoverer.py      # LLM rule generation for ALF
            │   │   └── impact_assessor.py      # Cross-case rule impact analysis
            │   ├── shared_libraries/           # Reusable domain logic (acting pipeline, ALF engine)
            │   ├── tools/                      # 18 Agent Tools (inference, learning, queue operations)
            │   ├── data/                       # Operational data, rule bases, eval results
            │   └── exemplary_data/             # Test cases, input PDFs, and exception queue configs
            │       └── exception_queue/        
            │           ├── erp_database.json   # Mock ERP reference data
            │           └── exception_queue.csv # Sample queue ingestion data
            ├── deployment/                     # Deployment scripts and Cloud configs
            ├── run_queue_cli.py                # Dedicated CLI for Exception Queue pipeline
            ├── run_acting_cli.py               # CLI for testing acting pipeline isolated
            ├── eval/                           # Schema-driven evaluation framework
            ├── tests/                          # Unit and integration tests
            └── pyproject.toml                  # Python dependencies
```

---

## 7. Setup & Installation

### Prerequisites
- Python 3.10+
- Google Cloud project with Vertex AI API enabled
- [uv](https://docs.astral.sh/uv/) for Python package management
- Google Agent Development Kit (ADK) installed

### Installation Steps
1. **Navigate and Install Dependencies:**
   ```bash
   cd python/agents/invoice-processing
   uv sync
   ```
2. **Configure Environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your GCP Project ID and Location
   ```
3. **Authenticate with GCP:**
   ```bash
   gcloud auth application-default login
   ```

---

## 8. Extending the System

- **Adding New Exception Classifications:** Update `EXCEPTION_TYPES` and the `_CLASSIFICATION_SYSTEM_PROMPT` in `invoice_processing/core/exception_classifier.py`.
- **Modifying Routing Logic:** Adjust the deterministic routing rules in the `assign_resolution_paths` tool within `invoice_processing/tools/tools.py`.
- **Domain Configuration:** Swap out `shared_libraries/invoice_master_data.yaml` to adapt the invoice processing pipeline to different document types.

---

## 9. Evaluation

The project includes an evaluation framework located in the `eval/` folder to continuously monitor accuracy. It provides:
- Deterministic field-by-field comparisons against ground truth (Free, instantaneous).
- LLM-as-Judge capabilities to evaluate holistic alignment (Optional).
- Financial tolerance configurations for numerical matches.

```bash
# Run full evaluation
uv run eval/eval.py --ground-truth invoice_processing/exemplary_data --agent-output invoice_processing/data/agent_output
```

---

## 10. Production & GCS Integration

For production deployment, local storage directories should be replaced with Google Cloud Storage (GCS) buckets.

- **Incoming Cases:** Mapped to `gs://{BUCKET}/incoming_cases/`
- **Agent Output:** Mapped to `gs://{BUCKET}/agent_output/`
- **ALF Output:** Mapped to `gs://{BUCKET}/alf_output/`
- **Configuration (Rules & Constitutions):** Mapped to `gs://{BUCKET}/config/`

### Configuration
Enable GCS in the `.env` file:
```bash
GCS_ENABLED=true
GCS_BUCKET=your-invoice-processing-bucket
GCS_INPUT_PREFIX=incoming_cases
GCS_OUTPUT_PREFIX=agent_output
GCS_ALF_PREFIX=alf_output
GCS_CONFIG_PREFIX=config
```
