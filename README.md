# auxilab-agent-ap-exceptions

> Agentic AI · AP exception queue triage, root-cause classification, resolution path assignment, and communication drafting

**Part of [AuxiLab](https://auxiliobits.com/auxilab) — Auxiliobits' open-source agentic AI lab for Finance and AP operations.**

---

## What This Does

<!-- TODO: Replace this section with a clear 2-3 sentence description of what the tool does,
     what problem it solves, and who would use it. -->

````markdown
# auxilab-agent-ap-exceptions

**auxilab-agent-ap-exceptions** is a production-grade, AI-powered **Accounts Payable (AP) Exception Handling** agent built using the **Google Agent Development Kit (ADK)**. It automates the complete invoice exception management lifecycle—from processing raw exception queues to generating resolution-ready outputs—through a robust multi-agent pipeline.

The system combines deterministic validation, AI reasoning, and human oversight to deliver accurate, auditable, and scalable exception handling for enterprise AP operations.

---

## Operating Modes

### Inference Mode

A fully autonomous, end-to-end processing pipeline that:

- Ingests batches of invoice exceptions from a CSV queue.
- Classifies each invoice exception by its root cause.
- Determines the appropriate resolution path.
- Prioritizes exceptions based on financial risk.
- Automatically resolves eligible cases using the Adaptive Learning Framework (ALF).

### Learning Mode

A human-in-the-loop workflow designed for Accounts Payable Subject Matter Experts (SMEs).

In this mode, AP managers can:

- Review exceptions that could not be resolved automatically.
- Propose new exception-handling rules.
- Validate proposed rules using automated safety and impact analysis.
- Approve validated rules into the production rule base, enabling future autonomous resolution.

---

## Pipeline Overview

For every invoice exception, the agent performs the following steps:

### Data Ingestion

- Reads invoice exceptions from `exception_queue.csv`.
- Cross-references each invoice against `erp_database.json`.
- Retrieves supporting ERP information including:
  - Purchase Orders (PO)
  - Goods Receipt Notes (GRN)
  - Vendor Master records
  - Payment history

### Root Cause Classification

Identifies the underlying cause of each exception, including:

- Vendor mismatch
- PO tolerance breach
- Duplicate invoice
- Missing Work Authorization (WAF)
- Tax/GST calculation errors
- Currency discrepancies
- Other Accounts Payable exception categories

### Multi-Agent Processing Pipeline

Each invoice passes through a structured 4-phase, 9-sub-agent pipeline:

```text
Classify
    ↓
Extract
    ↓
Phase 1
    ↓
Phase 2
    ↓
Phase 3
    ↓
Phase 4
    ↓
Transform
    ↓
Output
    ↓
Audit
```

### Multi-Layer Validation

Every output is validated through a three-layer critic framework:

1. Deterministic business-rule validation.
2. LLM-based rule discovery with SHA-256 response caching.
3. Ultra-conservative per-group validation to ensure financial accuracy and consistency.

### Adaptive Learning Framework (ALF)

The Adaptive Learning Framework (ALF) automatically applies previously approved exception-handling rules to eligible invoices. Matching cases are corrected deterministically without re-running the complete AI pipeline, improving throughput while maintaining consistency and auditability.

### Risk Prioritization

Exceptions requiring human intervention are:

- Assigned a normalized financial risk score.
- Ranked according to business impact.
- Mapped to structured resolution paths for AP teams.

### Automated Communication

For exceptions requiring manual review, the agent automatically generates:

- Vendor communication emails.
- Internal escalation notes.
- Resolution summaries.

### Audit and Compliance

Every decision made by the system is fully traceable through comprehensive audit logs, including:

- Classification decisions.
- Validation results.
- Rule matches.
- Automatic corrections.
- Agent execution history.

This provides complete transparency, regulatory compliance, and audit readiness for enterprise financial operations.
````


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
