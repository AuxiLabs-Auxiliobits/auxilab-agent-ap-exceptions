# auxilab-agent-ap-exceptions

> Agentic AI · AP exception queue triage, root-cause classification, resolution path assignment, and communication drafting

**Part of [AuxiLab](https://auxiliobits.com/auxilab) — Auxiliobits' open-source agentic AI lab for Finance and AP operations.**

---

## What This Does

<!-- TODO: Replace this section with a clear 2-3 sentence description of what the tool does,
     what problem it solves, and who would use it. -->

auxilab-agent-ap-exceptions is a production-grade, AI-powered Accounts Payable Exception Handling agent built on Google Agent Development Kit (ADK). It automates the full lifecycle of invoice exception management — from ingesting a raw exception queue to generating resolution-ready outputs — using a multi-layer agentic pipeline.

The agent operates in two modes:

Inference Mode — Fully autonomous end-to-end processing: ingests a batch exception CSV queue, classifies each invoice anomaly by root cause, assigns a human-readable resolution path, prioritizes exceptions by financial risk, and auto-resolves cases where ALF correction rules apply.

Learning Mode — A human-in-the-loop SME interface where AP managers review rejected cases, propose new exception rules (with automatic safety and impact validation), and approve them into the live rule base for future autonomous resolution.

What the pipeline does for every invoice exception:
Ingests the AP exception queue from CSV (exception_queue.csv) and cross-references against the ERP database (erp_database.json) for PO, GRN, vendor master, and payment history data.

Classifies root causes across categories: vendor mismatch, PO tolerance breach, duplicate invoice, missing work authorization (WAF), tax/GST calculation error, currency discrepancy, and more.

Validates through a 4-phase, 9-sub-agent acting pipeline (Classify → Extract → Phase 1–4 → Transform → Output → Audit).

Investigates outputs with a 3-layer critic agent (deterministic checks → LLM rule discovery with SHA-256 caching → per-group ultra-conservative validation).

Applies the Adaptive Learning Framework (ALF) to auto-correct cases that match approved exception rules — deterministically, without re-running the full pipeline.

Prioritizes remaining human exceptions by normalized risk score and assigns structured resolution paths.

Drafts vendor communication emails and internal escalation notes for every case requiring human intervention.

Logs a full audit trail of all decisions, rule matches, and corrections for financial compliance.

---

## Tools / Capabilities

<!-- TODO: List each tool or agent step with a one-line description.
     Example:
     | Tool | Description |
     |------|-------------|
     | invoice_extractor | Extracts structured fields from raw invoice text |
-->

| Name | Description |
|------|-------------|
| _tool_1_ | _description_ |
| _tool_2_ | _description_ |

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
# Add any other required keys
```

---

## Usage

```python
# TODO: Add a realistic usage example with a sample input and the expected output.
# This is mandatory for submission.
```

### Run the Demo

```bash
python demo/demo.py
```

---

## Example

**Input:**
```json
{
  "TODO": "replace with a realistic sample input"
}
```

**Output:**
```json
{
  "TODO": "replace with the expected output"
}
```

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Known Limitations

<!-- TODO: Be honest about what the tool does not handle yet.
     Example: "Does not support multi-currency invoices." -->

- _Add known limitations here before submission_

---

## Built By

| Name | GitHub | Role |
|------|--------|------|
| _Team Member 1_ | [@handle](https://github.com/handle) | _Role_ |
| _Team Member 2_ | [@handle](https://github.com/handle) | _Role_ |
| _Team Member 3_ | [@handle](https://github.com/handle) | _Role_ |

Built during the **AuxiLab Founding Hackathon** by [Auxiliobits Technologies](https://auxiliobits.com).

---

## Licence

MIT — see [LICENSE](./LICENSE)
