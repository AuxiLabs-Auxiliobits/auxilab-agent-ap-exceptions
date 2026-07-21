# AP Exception Handling Agent

LangGraph-orchestrated workflow with **selective Claude AI nodes** for AP
exception triage, classification, routing, communication drafting, and priority
queue generation.

> **Brief reference:** This is a realisation of **Auxiliobits Build Brief #5 — AP
> Exception Handling Agent** (Difficulty ⭐⭐⭐⭐). Intended publication identifier:
> `auxilab-agent-ap-exceptions`. The sample queue in [sample_data/exception_queue.csv](sample_data/exception_queue.csv)
> matches the brief's mandated distribution (25 rows: 8 Price Variance, 5 Missing PO,
> 4 Duplicate, 4 Quantity Mismatch, 4 Unapproved Vendor) using real enterprise SaaS
> vendor names for demo familiarity.

> **Architectural principle:** Use AI for ambiguity. Use deterministic code
> for certainty.

## Quickstart

Requires Python 3.11+. **No API key needed** — with no key configured the whole
pipeline runs offline in deterministic mock mode.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -e .

python ui.py                       # → http://localhost:7860
```

Click **Load sample**, then **Run agent**. The UI returns KPIs, a per-invoice
table, the drafted communications, the rejected rows, and a downloadable JSON
report.

Other entry points:

```bash
gradio ui.py                                   # same UI, with hot reload
python cli.py examples/sample_exceptions.csv   # text summary to stdout
```

Both call into [app/standalone.py](app/standalone.py), which runs the same
LangGraph pipeline with an in-memory store — exactly as the test suite does.

## Pipeline

```
ingest ─► classify (AI) ─► severity_validator ─► route (rules)
                                                      │
                       ┌──────────────────────────────┤
                       ▼                              ▼
                  draft (AI)                    prioritize
                       │                              │
                       └──────────────┬───────────────┘
                                      ▼
                                  persist ─► review
```

| Node | Type | Tech |
|---|---|---|
| `ingest_node` | Deterministic | Pandas + Pydantic |
| `classify_node` | **AI** | Claude (tool-use) |
| `severity_validator` | Deterministic | Threshold rules |
| `route_node` | Deterministic | YAML rules engine |
| `draft_node` | **AI** | Claude (tool-use) |
| `prioritize_node` | Deterministic | Weighted scoring |
| `persist_node` | Deterministic | Filesystem |

## Where AI is — and isn't

- **AI:** `classify_node` (semantic classification of messy exception
  descriptions) and `draft_node` (natural-language drafting of vendor /
  internal / Slack / finance comms).
- **Deterministic:** every other node — ingestion, severity, routing rules,
  prioritization, persistence. These are all reproducible, replayable, and
  auditable.

The AI's severity suggestion is preserved as `severity_ai_suggested` for drift
monitoring, but the canonical `severity` field is **always** set by the
deterministic threshold validator.

Tool-use is **forced on every provider** — no model can reply with free text.
The same JSON-Schema tool spec ([app/ai/schemas.py](app/ai/schemas.py)) is
translated to each provider's native shape at call time, so downstream nodes
never see provider-specific output.

## AI providers

With `AI_PROVIDER` unset (the default), the client auto-detects a backend by
precedence:

1. `ANTHROPIC_API_KEY` set → **Claude** (preferred).
2. else `GEMINI_API_KEY` set → **Google Gemini**.
3. else `AZURE_OPENAI_API_KEY` + `AZURE_CHAT_OPENAI_ENDPOINT` set → **Azure OpenAI**.
4. else → **deterministic mock mode**.

Set `AI_PROVIDER` to `anthropic` | `gemini` | `azure` | `mock` to **pin** one
instead. Pin it whenever more than one key is configured — otherwise the
higher-precedence provider silently wins and a lower-precedence key you meant to
test is ignored. A pinned provider missing its credentials falls back to **mock,
never to a different live provider**: silently billing a provider the operator
didn't choose is worse than running offline.

| Env var | Default | Purpose |
|---|---|---|
| `CLASSIFY_MODEL` | `claude-opus-4-7` | Anthropic classifier |
| `DRAFT_MODEL` | `claude-sonnet-4-6` | Anthropic drafter |
| `GEMINI_CLASSIFY_MODEL` | `gemini-2.5-flash` | Gemini classifier |
| `GEMINI_DRAFT_MODEL` | `gemini-2.5-flash` | Gemini drafter |
| `AZURE_OPENAI_DEPLOYMENT` | `gpt-4o-mini` | Azure deployment (both classify and draft) |
| `AZURE_OPENAI_VERSION` | `2024-10-21` | Azure API version |

Current Anthropic ids: `claude-opus-4-8` (most capable), `claude-opus-4-7`,
`claude-sonnet-5`, `claude-sonnet-4-6`, `claude-haiku-4-5` (fastest/cheapest).
Both Gemini defaults are Flash on purpose — `gemini-2.5-pro` has a 0 RPM free
tier, so every request 429s unless you have a paid key.

### Switching provider without a restart

The UI's **⚙️ Advanced Settings** panel picks the provider, takes its API key,
and offers a model dropdown — applied immediately, no restart.

Values entered there live in the **server process only**. They are never written
to `.env`, are shared by every browser tab hitting that instance, and are lost on
restart. Use `.env` for anything persistent, then hit **Reload .env** — which
also discards anything typed in the panel, so the file wins. Because it is
process-global, the panel is meant for a local single-user demo; don't expose
that instance beyond localhost.

Leaving the model box blank keeps whatever `.env` already configured.

### Mock mode

With no provider key set, the client returns deterministic mock classifications
(echoing the ERP-declared type with confidence 0.82 when in-taxonomy, 0.45 for
"Other") and a stock draft. The entire pipeline runs offline end to end.

### Vendor history is stateful across runs

With `VENDOR_HISTORY_ENABLED=true` (the default), every run appends to per-vendor
reliability profiles in `VENDOR_PROFILES_PATH`, and those profiles **enrich the
classifier prompt on subsequent runs**. Two runs over the same CSV can therefore
produce different classifications — by design, but surprising if you're diffing
output or scripting a demo. Set `VENDOR_HISTORY_ENABLED=false` (or delete the
profiles file) when you need strict run-to-run reproducibility.

This applies in mock mode too: "deterministic" describes the AI client, not
independence from prior runs.

## Rules engine

Resolution policy lives in [app/rules/policies/default.yaml](app/rules/policies/default.yaml).
First match wins; a catch-all rule (`when: {}`) is enforced at load time. Each
decision carries the matched rule ID, policy version, and a per-key firing trace
— sufficient for SOX walkthroughs.

`AUTO_APPROVE_MAX_AMOUNT` (default 10,000) is a hard materiality backstop: an
invoice at or above it can never auto-approve regardless of what the policy says
— it is routed to MANUAL_REVIEW and the override is recorded in the trace.

## Severity policy (deterministic)

| Severity | Rule |
|---|---|
| HIGH | `amount > 25,000` OR `days_outstanding > 30` |
| MEDIUM | `5,000 ≤ amount ≤ 25,000` |
| LOW | `amount < 5,000` |

Tunable via `SEVERITY_HIGH_AMOUNT`, `SEVERITY_HIGH_DAYS`,
`SEVERITY_MEDIUM_AMOUNT_MIN`.

## Priority scoring

```
priority_score =
    w_amount   * normalize(invoice_amount, 0, 100_000)
  + w_age      * normalize(days_outstanding, 0, 60)
  + w_severity * severity_weight
  + w_path     * resolution_path_weight
  + w_conf     * (1 - confidence_score)
```

Defaults: `(0.30, 0.25, 0.25, 0.15, 0.05)`. Bucketization:

- HIGH: `score ≥ 0.70` **or** `severity == HIGH`
- MEDIUM: `0.40 ≤ score < 0.70`
- LOW: `score < 0.40`

Tie-break order: `(-score, -days_outstanding, -amount, invoice_id)`.

## Configuration

Everything is optional — with no `.env` at all the pipeline runs in offline mock
mode. These are the **only** variables the CLI / Gradio path reads; all of them
are in [.env.example](.env.example) with their defaults.

| Group | Variables |
|---|---|
| Provider | `AI_PROVIDER`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `AZURE_OPENAI_API_KEY`, `AZURE_CHAT_OPENAI_ENDPOINT` |
| Models | `CLASSIFY_MODEL`, `DRAFT_MODEL`, `GEMINI_CLASSIFY_MODEL`, `GEMINI_DRAFT_MODEL`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_VERSION` |
| AI calls | `AI_MAX_CONCURRENCY`, `AI_MAX_RETRIES`, `AI_TIMEOUT_SECONDS`, `AI_TASK_TIMEOUT_SECONDS` |
| Routing | `RULES_POLICY_PATH`, `AUTO_APPROVE_MAX_AMOUNT` |
| Severity | `SEVERITY_HIGH_AMOUNT`, `SEVERITY_HIGH_DAYS`, `SEVERITY_MEDIUM_AMOUNT_MIN` |
| Scoring | `W_AMOUNT`, `W_AGE`, `W_SEVERITY`, `W_PATH`, `W_CONF`, `HIGH_THRESHOLD`, `MEDIUM_THRESHOLD` |
| Vendor history | `VENDOR_HISTORY_ENABLED`, `VENDOR_PROFILES_PATH` |
| Output | `ARTIFACT_DIR` |

Anything else in [app/config.py](app/config.py) — auth, database, run queue,
Supabase, outbound email/Slack, CORS, rate limiting — belongs to the optional
FastAPI service in `app/api/` and has **no effect** on `cli.py` / `ui.py`. Two
specifics worth knowing: `LOG_LEVEL` is applied by that service's startup only,
so it does nothing here, and the standalone runner always uses the in-memory run
store regardless of `RUN_STORE_BACKEND` / `DB_PERSISTENCE_ENABLED`.

## Security notes

- User-supplied free text is wrapped in `<exception>` / `<context>` delimiters
  with the system prompt instructing the model to treat it as data, not
  instructions.
- Draft outputs run through a PII redaction pass (SSN-style, long card numbers,
  bank account references) before persisting.
- Tool-use is forced — the model cannot reply with free text in the
  classification or drafting nodes.
- Nothing is sent. Every drafted communication is agent output staged for human
  review.

## Folder structure

```
ui.py              Gradio interface
cli.py             Terminal entry point
app/
├── standalone.py  In-process entry point used by both of the above
├── ai/            AI client, tool-use schemas, prompts
├── graph/         LangGraph builder + RunState + nodes
│   └── nodes/     ingest, classify, severity, route, draft,
│                  prioritize, persist, error_handler
├── rules/         Rules engine + YAML policies
├── scoring/       Priority scoring engine
├── schemas/       Pydantic models
├── vendor/        Vendor reliability profiles
├── audit/         Append-only audit event helpers
├── api/           Optional FastAPI service (not used by ui.py / cli.py)
└── config.py
examples/          Sample exception queue
sample_data/       Brief-mandated 25-row queue
```

## License

Proprietary — internal enterprise template.
