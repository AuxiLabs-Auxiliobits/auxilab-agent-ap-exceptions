# auxilab-agent-ap-exceptions

> Agentic AI · AP exception queue triage, root-cause classification, resolution path assignment, and communication drafting

**Part of [AuxiLab](https://auxiliobits.com/auxilab) — Auxiliobits' open-source agentic AI lab for Finance and AP operations.**

---

## What This Does

**auxilab-agent-ap-exceptions** is an enterprise-grade AI pipeline that automates Accounts Payable (AP) exception management end-to-end. It eliminates manual triage bottlenecks by ingesting batch exception queues, cross-referencing ERP records (Purchase Orders, Goods Receipt Notes, and Vendor Master data) to produce evidence-grounded root-cause classifications, then deterministically routing each exception to the correct team with a calculated priority score, SLA, and a ready-to-send vendor or internal communication draft. AP operations teams, finance controllers, and procurement specialists use this tool to prevent duplicate payments, unblock vendor cash flow, and continuously improve accuracy through a human-in-the-loop Adaptive Learning Framework (ALF).

---

## Tools / Capabilities

| Name | Description |
|------|-------------|
| `ingest_exception_queue` | Ingests CSV or JSON exception queues and uses an LLM to auto-map any custom column headers to the canonical AP schema |
| `classify_exceptions` | Cross-references each invoice against ERP data using Gemini Pro or Claude (switchable via `LLM_PROVIDER`) to assign a root-cause type with a confidence score |
| `assign_resolution_paths` | Deterministically calculates priority scores (0–100), SLAs (24h–72h), payment block flags, and resolution owners from a YAML rule engine — no LLM involved |
| `draft_communications` | Generates professional vendor query emails and internal escalation notes for each exception that requires outreach |
| `build_priority_output` | Produces a ranked work queue (HIGH → MEDIUM → LOW) and an executive dashboard with blocked payment value, duplicate risk, and auto-resolved counts |
| `run_exception_queue` | Single-call entry point that runs all five pipeline steps in sequence and returns the complete result |
| `run_inference` | Runs the full document-level pipeline: a 9-sub-agent invoice extraction engine, a 3-layer compliance audit, and a rule-based correction engine |
| `discover_safe_rule` | Lets an SME teach the system a new correction rule in plain English; the rule is validated against all historical cases before it is saved |
| `revise_safe_rule` | Modifies an existing learned rule with automated cross-case safety validation to ensure zero collateral damage |

---

## Installation

```bash
# Clone the repo
git clone https://github.com/AuxiLabs-Auxiliobits/auxilab-agent-ap-exceptions.git
cd auxilab-agent-ap-exceptions

# Navigate to the agent directory
cd python/agents/invoice-processing

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies (recommended: uv)
uv sync

# Or with pip
pip install -r invoice_processing/requirements.txt
```

### Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

```env
# Choose your LLM provider: "gemini" (default) or "claude"
LLM_PROVIDER=gemini

# Gemini — required when LLM_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key_here

# Claude — required when LLM_PROVIDER=claude
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Demo mode — set to true to run with no API key (returns stub responses)
DEMO_MODE=false
```

> **Switching providers is a one-line change.** Set `LLM_PROVIDER=claude` and add your `ANTHROPIC_API_KEY` — no code changes needed.

---

## Usage

```python
from invoice_processing.agent import run_exception_queue

# Run the full 5-step batch exception queue pipeline
result = run_exception_queue(
    file_paths=["invoice_processing/exemplary_data/exception_queue/exception_queue.csv"],
    debug=True
)

# Executive dashboard metrics
dashboard = result.get("dashboard", {})
bv = dashboard.get("business_value_metrics", {})
print(f"Total invoices   : {dashboard.get('total_invoices')}")
print(f"Payments blocked : {dashboard.get('payments_blocked')}")
print(f"Blocked value    : ${bv.get('blocked_payment_value', 0):,.2f}")
print(f"Duplicate risk   : ${bv.get('potential_duplicate_payment_value', 0):,.2f}")

# Priority queue — highest risk first
for invoice in result.get("priority_queue", []):
    print(f"\n{invoice['invoice_id']} | {invoice['vendor_name']}")
    print(f"  Priority : {invoice['priority_tier']} (score {invoice['normalized_priority_score']}) | SLA {invoice['sla_hours']}h")
    for exc in invoice.get("final_exception_list", []):
        print(f"  -> {exc['primary_type']} ({exc['confidence']*100:.0f}% confidence)")
        print(f"     Action: {exc['recommended_action']}")
```

### Run the Demo

```bash
# Batch exception queue pipeline (CLI)
python run_queue_cli.py \
  --file invoice_processing/exemplary_data/exception_queue/exception_queue.csv \
  --debug

# Web dashboard — open http://localhost:5001
python ui/app.py

# Single document inference
python run_single_inference_cli.py --case case_001
```

---

## Example

**Input — TC-010: Invoice referencing a non-existent PO**

```json
{
  "invoice_id": "TC-010",
  "vendor_name": "Epsilon Parts",
  "invoice_number": "INV-E001",
  "invoice_amount": 4500,
  "currency": "USD",
  "po_number": "PO-INVALID-999",
  "invoice_date": "2026-05-12"
}
```

**Output:**

```json
{
  "invoice_id": "TC-010",
  "vendor_name": "Epsilon Parts",
  "priority_tier": "HIGH",
  "normalized_priority_score": 85.0,
  "payment_blocked": true,
  "sla_hours": 24,
  "resolution_owners": ["Procurement"],
  "final_exception_list": [
    {
      "primary_type": "PO Not Found",
      "root_cause_hypothesis": "Purchase order PO-INVALID-999 does not exist in the ERP database.",
      "recommended_action": "Contact vendor to confirm the correct PO number or ask Procurement to issue a retroactive PO.",
      "confidence": 0.98,
      "evidence_used": "PO-INVALID-999 cross-referenced against erp_database.json — no matching record found."
    }
  ],
  "drafted_communication": {
    "communication_type": "internal_po_request",
    "draft": "Hi [Procurement Team], invoice INV-E001 from Epsilon Parts ($4,500) is on hold as PO-INVALID-999 cannot be found in the system. Please raise a valid PO within 3 business days to unblock payment. Reference: TC-010."
  }
}
```

**Input — TC-005: Exact duplicate invoice**

```json
{
  "invoice_id": "TC-005",
  "vendor_name": "BetaTech Corp",
  "invoice_number": "INV-B001",
  "invoice_amount": 5000,
  "currency": "USD",
  "po_number": "PO-6002",
  "invoice_date": "2026-05-05"
}
```

**Output:**

```json
{
  "invoice_id": "TC-005",
  "priority_tier": "HIGH",
  "normalized_priority_score": 91.0,
  "payment_blocked": true,
  "sla_hours": 24,
  "resolution_owners": ["AP Manager"],
  "final_exception_list": [
    {
      "primary_type": "Exact Duplicate Invoice",
      "root_cause_hypothesis": "INV-B001 from BetaTech Corp for $5,000 already exists in ERP payment history with an identical amount.",
      "recommended_action": "Place on hold immediately and initiate a duplicate payment investigation.",
      "confidence": 1.0,
      "evidence_used": "ERP historical_invoices: INV-B001, BetaTech Corp, $5,000 USD — exact match on vendor, invoice number, and amount."
    }
  ]
}
```

---

## Running Tests

```bash
# Exception queue integration test
python test_exception_queue.py

# Schema mapper unit test
python test_schema_mapper.py

# Classifier unit test
python test_classify.py

# Evaluation framework (field-by-field accuracy scoring)
uv run eval/eval.py \
  --ground-truth invoice_processing/exemplary_data \
  --agent-output invoice_processing/data/agent_output
```

---

## Known Limitations

- **Language & Localization**: Optimized for English-language invoices; multi-language OCR and automated translation are not natively supported.
- **Real-Time FX Conversion**: Currency mismatches are detected and flagged, but live foreign exchange rate conversion is not applied during tolerance checks.
- **Line-Item Reconciliation**: Exception classification operates at the invoice header level; complex line-item splits against partial goods receipts are not reconciled.
- **Mock ERP Grounding**: ERP lookups query a static `erp_database.json` file; live SQL or REST API integrations require a custom adapter.
- **PDF Quality**: Invoice extraction accuracy depends on the PDF text layer; scanned or low-resolution documents may reduce field extraction confidence.

---

## Built By

| Name | GitHub | Role |
|------|--------|------|
| Rohan Walia | [@rohanwalia1](https://github.com/rohanwalia1) | Backend Developer |
| Pawandeep Singh | [@pawandeepsingh1](https://github.com/pawandeepsingh1) | Frontend Developer |

Built during the **AuxiLab Founding Hackathon** by [Auxiliobits Technologies](https://auxiliobits.com).

---
