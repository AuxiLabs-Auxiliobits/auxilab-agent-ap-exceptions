# auxilab-agent-ap-exceptions

> Agentic AI · AP exception queue triage, root-cause classification, resolution path assignment, and communication drafting

**Part of [AuxiLab](https://auxiliobits.com/auxilab) — Auxiliobits' open-source agentic AI lab for Finance and AP operations.**

---

## What This Does

**auxilab-agent-ap-exceptions** is an enterprise-grade agentic AI pipeline powered by Google's Agent Development Kit (ADK) and Gemini 2.5 Pro that automates Accounts Payable (AP) exception management and triage. It eliminates manual diagnosis bottlenecks by ingesting batch exception queues, cross-referencing simulated ERP records (POs, GRNs, and Vendor Master data) to establish root causes, and deterministically routing resolutions with calculated priority scores, dynamic SLAs, and automated communication drafts. AP operations teams, controllers, and finance specialists use this tool to prevent duplicate payments, unblock vendor cash flow, and continuously evolve system accuracy through an interactive human-in-the-loop Adaptive Learning Framework (ALF).

---

## Tools / Capabilities

| Name | Description |
|------|-------------|
| `ingest_exception_queue` | Ingests and maps multi-format exception queues (CSV/JSON) into a canonical schema while validating headers against source fields |
| `classify_exceptions` | Utilizes Gemini 2.5 Pro and evidence-based ERP matching to identify root-cause hypotheses (e.g., duplicate detection, PO not found, tolerance breach) |
| `assign_resolution_paths` | Deterministically calculates priority scores, dynamic SLAs, ownership routing, and payment block/escalation decisions without LLM hallucination |
| `draft_communications` | Automatically generates contextual vendor and internal escalation emails based on extracted evidence and missing data requirements |
| `build_priority_output` | Assembles a sorted priority work queue alongside an executive dashboard tracking blocked value, duplicate risk, and valid invoice metrics |
| `run_inference` | Executes the core 9-agent Acting Pipeline (Intake, PO matching, Status validation, EWAF checks) paired with optional investigation audits |
| `discover_safe_rule` | Enables interactive SME teaching via the Adaptive Learning Framework (ALF), automatically validating proposed rules against historical cross-case impact |
| `revise_safe_rule` | Modifies existing business correction rules with an automated safety loop to ensure zero collateral damage across prior cases |

---

## Installation

```bash
# Clone the repo
git clone https://github.com/AuxiLabs-Auxiliobits/auxilab-agent-ap-exceptions.git
cd auxilab-agent-ap-exceptions

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

```env
ANTHROPIC_API_KEY=your_key_here
GOOGLE_API_KEY=your_gemini_api_key_here
PROJECT_ID=your-gcp-project-id
LOCATION=us-central1
```

---

## Usage

```python
from invoice_processing.agent import run_exception_queue

# Run the batch exception queue pipeline against sample exception files
result = run_exception_queue(
    file_paths=["python/agents/invoice-processing/invoice_processing/exemplary_data/exception_queue/exception_queue.csv"],
    debug=True
)

# Access the executive dashboard metrics
dashboard = result.get("dashboard", {})
print(f"Total Invoices Processed: {dashboard.get('total_invoices')}")
print(f"Payments Blocked: {dashboard.get('payments_blocked')}")
print(f"Escalations Required: {dashboard.get('escalations_required')}")

# Inspect high-priority exception items
for invoice in result.get("priority_queue", []):
    print(f"\nInvoice: {invoice['invoice_id']} | Priority: {invoice['priority_tier']} | Score: {invoice['normalized_priority_score']}")
    for exc in invoice.get("final_exception_list", []):
        print(f"  -> Root Cause: {exc['primary_type']} ({exc['root_cause_hypothesis']})")
```

### Run the Demo

```bash
python python/agents/invoice-processing/run_queue_cli.py --file python/agents/invoice-processing/invoice_processing/exemplary_data/exception_queue/exception_queue.csv --debug
```

---

## Example

To run this specific test case from `exception_queue.csv`, execute:

```bash
python python/agents/invoice-processing/run_queue_cli.py --file python/agents/invoice-processing/invoice_processing/exemplary_data/exception_queue/exception_queue.csv --debug
```

**Input (Test Case TC-010 from `exception_queue.csv`):**
```json
{
  "exceptions": [
    {
      "invoice_id": "TC-010",
      "vendor_name": "Epsilon Parts",
      "invoice_number": "INV-E001",
      "invoice_amount": "4500",
      "currency": "USD",
      "po_number": "PO-INVALID-999",
      "invoice_date": "2026-05-12"
    }
  ]
}
```

**Output:**
```json
{
  "dashboard": {
    "total_invoices": 1,
    "payments_blocked": 1,
    "escalations_required": 1,
    "high_priority_count": 1
  },
  "priority_queue": [
    {
      "invoice_id": "TC-010",
      "invoice_number": "INV-E001",
      "vendor_name": "Epsilon Parts",
      "invoice_amount": 4500.0,
      "priority_tier": "HIGH",
      "normalized_priority_score": 85.0,
      "payment_blocked": true,
      "escalation_required": true,
      "sla_hours": 24,
      "resolution_owners": [
        "AP_Level_2",
        "Procurement"
      ],
      "final_exception_list": [
        {
          "primary_type": "PO Not Found",
          "root_cause_hypothesis": "Purchase order PO-INVALID-999 does not exist in the ERP database.",
          "recommended_action": "Contact vendor to confirm valid PO number or request procurement to issue retroactive PO.",
          "confidence": 0.98,
          "evidence_used": "Cross-referenced PO-INVALID-999 against erp_database.json; no record found."
        }
      ]
    }
  ]
}
```

---

## Running Tests

```bash
python python/agents/invoice-processing/test_exception_queue.py
```

---

## Known Limitations

- **Language & Localization**: Currently optimized for English-language invoices and communication drafts; multi-language OCR and automated translation are not natively handled.
- **Real-Time FX Conversion**: While currency mismatches are flagged during classification, live real-time foreign exchange rate conversion is not calculated during numerical tolerance checks.
- **Line-Item Split Reconciliation**: Exception classification operates primarily at the header/total level rather than reconciling complex, multi-page line-item splits against partial 3-way goods receipts.
- **Mock ERP State Grounding**: Database lookups query static JSON/YAML reference stores (`erp_database.json`); live bidirectional SQL or REST API ERP integrations require custom adapter implementations.

---

## Built By

| Name | GitHub | Role |
|------|--------|------|
| Rohan Walia | [@rohanwalia1](https://github.com/rohanwalia1) | Backend Developer |
| Pawandeep Singh | [@pawandeepsingh1](https://github.com/pawandeepsingh1) | Frontend Developer |

Built during the **AuxiLab Founding Hackathon** by [Auxiliobits Technologies](https://auxiliobits.com).

---

## Licence

MIT — see [LICENSE](./LICENSE)
