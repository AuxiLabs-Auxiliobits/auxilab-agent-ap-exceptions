# AP Exception Handling Agent

LangGraph-orchestrated workflow with **selective Claude AI nodes** for AP
exception triage, classification, routing, communication drafting, and
priority queue generation.

> **Brief reference:** This is a realisation of **Auxiliobits Build Brief #5 — AP
> Exception Handling Agent** (Difficulty ⭐⭐⭐⭐). Intended publication identifier:
> `auxilab-agent-ap-exceptions`. The sample queue in [sample_data/exception_queue.csv](sample_data/exception_queue.csv)
> matches the brief's mandated distribution (25 rows: 8 Price Variance, 5 Missing PO,
> 4 Duplicate, 4 Quantity Mismatch, 4 Unapproved Vendor) using real enterprise SaaS
> vendor names for demo familiarity.

> **Architectural principle:** Use AI for ambiguity. Use deterministic code
> for certainty.

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
| `persist_node` | Deterministic | Filesystem (swap for Postgres+S3) |

## Quickstart (local Python)

```bash
pip install -e .

# Optional — set your Anthropic key. If unset, the pipeline runs in
# deterministic mock mode (no API calls) so you can verify wiring offline.
cp .env.example .env

# Start the API (use `python -m uvicorn` to avoid PATH issues on Windows)
python -m uvicorn app.api.main:app --reload
# API → http://localhost:8000  (interactive docs at /docs)
```

> On Windows / PowerShell, the bare `uvicorn` command may fail with
> `CommandNotFoundException` if your Python Scripts directory isn't on PATH.
> `python -m uvicorn …` always works.

The UI is the **React console** in `../Frontend` (run `npm run dev`, or use the
Docker quickstart below). The API is headless — drive it with the console, the
REST API, or `curl`.

## Quickstart (Docker)

```bash
# The React console bakes its Clerk publishable key at build time:
export VITE_CLERK_PUBLISHABLE_KEY=pk_test_...   # (Windows PowerShell: $env:VITE_CLERK_PUBLISHABLE_KEY="pk_test_...")
docker compose up --build
# API → http://localhost:8000
# Web (React reviewer console) → http://localhost:8080
```

The React console (`web` service) is served by nginx, which reverse-proxies
`/v1`, `/healthz`, and `/readyz` to the `api` service — so the browser talks to
a single origin. It is the only UI; the backend is otherwise headless.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/runs` | Upload CSV/JSON, run the workflow |
| GET | `/v1/runs/{id}` | Run summary |
| GET | `/v1/runs/{id}/results` | Per-invoice classification, resolution, draft |
| GET | `/v1/runs/{id}/metrics` | Dashboard metrics + queues |
| GET | `/v1/runs/{id}/drafts/{invoice_id}` | Fetch a draft |
| PATCH | `/v1/runs/{id}/drafts/{invoice_id}` | Edit a draft |
| POST | `/v1/runs/{id}/approve` | Approve the run |
| GET | `/v1/runs/{id}/audit` | Append-only audit log |
| GET | `/healthz` | Liveness (process up) |
| GET | `/readyz` | Readiness — probes the run store (+ DB when persistence is on); 503 if a dependency is down |
| GET | `/metrics` | Prometheus metrics: runs, AI tokens + estimated cost, comms sends |

Example:

```bash
curl -F "file=@sample_data/exception_queue.csv" -F "tenant_id=acme" \
     http://localhost:8000/v1/runs
```

## Where AI is — and isn't

- **AI:** `classify_node` (semantic classification of messy exception
  descriptions) and `draft_node` (natural-language drafting of vendor /
  internal / Slack / finance comms).
- **Deterministic:** every other node — ingestion, severity, routing rules,
  prioritization, persistence. These are all reproducible, replayable, and
  auditable.

The AI's severity suggestion is preserved as `severity_ai_suggested` for
drift monitoring, but the canonical `severity` field is **always** set by
the deterministic threshold validator.

## Rules engine

Resolution policy lives in [app/rules/policies/default.yaml](app/rules/policies/default.yaml).
First match wins; a catch-all rule (`when: {}`) is enforced at load time.
Each decision carries the matched rule ID, policy version, and a per-key
firing trace — sufficient for SOX walkthroughs.

## AI providers

The AI client picks a backend at startup using this precedence:

1. `ANTHROPIC_API_KEY` set → **Claude** (preferred).
2. else `GEMINI_API_KEY` set → **Google Gemini** (fallback #1).
3. else `AZURE_OPENAI_API_KEY` + `AZURE_CHAT_OPENAI_ENDPOINT` set → **Azure OpenAI** (fallback #2).
4. else → **deterministic mock mode**.

Models are independently configurable per provider:

| Env var | Default | Purpose |
|---|---|---|
| `CLASSIFY_MODEL` | `claude-opus-4-7` | Anthropic classifier |
| `DRAFT_MODEL` | `claude-sonnet-4-6` | Anthropic drafter |
| `GEMINI_CLASSIFY_MODEL` | `gemini-2.5-flash` | Gemini classifier |
| `GEMINI_DRAFT_MODEL` | `gemini-2.5-flash` | Gemini drafter |
| `AZURE_OPENAI_DEPLOYMENT` | `gpt-4o-mini` | Azure deployment (used for both classify and draft) |
| `AZURE_OPENAI_VERSION` | `2024-10-21` | Azure API version |
| `AZURE_CHAT_OPENAI_ENDPOINT` | — | e.g. `https://<resource>.openai.azure.com/` |

Tool-use is **forced on both providers** — neither model can reply with
free text. The same JSON-Schema tool spec ([app/ai/schemas.py](app/ai/schemas.py))
is translated to each provider's native shape at call time, so downstream
nodes never see provider-specific output.

### Mock mode

When neither API key is set, the client returns deterministic mock
classifications (echoing the ERP-declared type with confidence 0.82 when
in-taxonomy, 0.45 for "Other") and a stock draft. The entire pipeline
runs offline end-to-end — useful for dev, CI, and demos.

## Folder structure

```
app/
├── api/           FastAPI routes + run executor + store
├── audit/         Append-only audit event helpers
├── ai/            Claude client, tool-use schemas, prompts
│   └── prompts/   System & per-template Markdown
├── graph/         LangGraph builder + RunState + nodes
│   └── nodes/     ingest, classify, severity, route, draft,
│                  prioritize, persist, error_handler
├── rules/         Rules engine + YAML policies
├── scoring/       Priority scoring engine
├── schemas/       Pydantic models
├── comms/         Email/Slack dispatch + providers
├── db/            Normalized SQLAlchemy models + repositories
├── vendor/        Vendor reliability profiles
├── observability/ Metrics + AI cost tracking
└── config.py
sample_data/
Dockerfile
docker-compose.yml
```

## Severity policy (deterministic)

| Severity | Rule |
|---|---|
| HIGH | `amount > 25,000` OR `days_outstanding > 30` |
| MEDIUM | `5,000 ≤ amount ≤ 25,000` |
| LOW | `amount < 5,000` |

## Priority scoring

```
priority_score =
    w_amount   * normalize(invoice_amount, 0, 100_000)
  + w_age      * normalize(days_outstanding, 0, 60)
  + w_severity * severity_weight
  + w_path     * resolution_path_weight
  + w_conf     * (1 - confidence_score)
```

Defaults: `(0.30, 0.25, 0.25, 0.15, 0.05)`. Tunable per tenant via env vars.

Bucketization:
- HIGH: `score ≥ 0.70` **or** `severity == HIGH`
- MEDIUM: `0.40 ≤ score < 0.70`
- LOW: `score < 0.40`

Tie-break order: `(-score, -days_outstanding, -amount, invoice_id)`.

## Database & migrations

The normalized persistence layer is managed with **Alembic**. `DATABASE_URL`
drives the target (SQLite by default; `postgresql+psycopg://…` for
Supabase/Postgres).

```bash
# apply all migrations (creates/updates the 9 normalized tables)
python -m alembic upgrade head

# after changing app/db/models.py — autogenerate the next migration
python -m alembic revision --autogenerate -m "describe change"

# roll back one step
python -m alembic downgrade -1
```

`init_db()`/`python -m scripts.init_db` (a bare `create_all`) remains for quick
local/dev use, but **production should use Alembic migrations** so schema
changes are versioned and reviewable. CI applies `upgrade head` + `downgrade
base` on every push.

## Durable run execution

By default a run executes as a fire-and-forget background task — fast, but a
restart mid-run loses it. Set `RUN_QUEUE_ENABLED=true` (requires a DB) to switch
to the **durable queue**: the uploaded input is persisted to the `run_jobs`
table and an in-process worker leases and executes it.

- **Durable** — a queued run survives a process restart.
- **Recoverable** — a run whose worker died mid-flight is re-leased after the
  lease TTL (`RUN_QUEUE_LEASE_SECONDS`) and re-executed; orphans are reclaimed
  on startup.
- **Retryable** — a failed execution is retried up to `RUN_QUEUE_MAX_ATTEMPTS`.
- **Scalable** — run multiple instances; the DB lease (atomic claim) keeps
  job pickup safe across processes. No Redis/Celery required.

`POST /v1/runs` returns immediately with `status=PENDING` (queued); poll
`GET /v1/runs/{id}` as usual. The worker is started/stopped by the app lifespan
and drains in-flight jobs on shutdown.

## Security notes

- API auth: set `AUTH_ENABLED=true` + `CLERK_ISSUER` to require a verified
  Clerk JWT on every `/v1/*` route, with per-tenant run scoping (a tenant only
  sees its own runs). The app refuses to boot in a protected environment
  (`ENVIRONMENT` starting `prod`/`stag`) if auth is off, CORS is unrestricted,
  live comms have no allowlist, or the run store is the non-durable in-memory
  backend.
- User-supplied free text is wrapped in `<exception>` / `<context>` delimiters
  with the system prompt instructing the model to treat them as data, not
  instructions.
- Draft outputs run through a PII redaction pass (SSN-style, long card
  numbers, bank account references) before persisting.
- Tool-use is forced — the model cannot reply with free text in classification
  or drafting nodes.
- Outbound comms are throttled by a per-domain daily cap and gated by a
  live-send domain allowlist; vendor emails resolve through a vendor master CSV
  (`VENDOR_MASTER_PATH`) and an unknown vendor is refused, not mis-delivered.

## Production hardening

- **CI**: GitHub Actions at the repo root (`.github/workflows/ci.yml`) runs
  backend (ruff, mypy [advisory], pytest, Alembic up/down) **and** frontend
  (eslint, vitest, `tsc` + `vite build`) jobs, plus a `pip-audit` gate.
- **Health**: `/readyz` actually probes the run store (and DB when persistence
  is on) and returns 503 when a dependency is unreachable — wire it to your
  orchestrator's readiness probe.
- **Observability**: `/metrics` exposes Prometheus counters for runs, per-call
  AI token usage + estimated USD cost, and comms sends.
- **Durability**: a durable run store that fails to initialize is fatal in a
  protected environment (no silent in-memory fallback). On shutdown, in-flight
  background runs are drained (`SHUTDOWN_DRAIN_SECONDS`).
- **Reproducible installs**: `requirements.lock` (generated with
  `pip-compile pyproject.toml -o requirements.lock`) fully pins the dependency
  tree. Use it for production/Docker images: `pip install -r requirements.lock`.
  Regenerate it after editing `pyproject.toml` dependencies.

## License

Proprietary — internal enterprise template.
