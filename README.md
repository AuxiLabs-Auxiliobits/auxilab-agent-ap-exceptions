# AP Exception Handling Agent — Monorepo

An AI-assisted **Accounts Payable exception triage** system: it ingests a queue
of invoice exceptions, classifies them with Claude, routes them through a
deterministic rules engine, drafts vendor/internal communications, and presents
everything in a reviewer console for human approval and sending.

This repository contains two parts:

| Folder | What it is | Stack |
|---|---|---|
| [`Backend/`](Backend/) | FastAPI service + LangGraph pipeline | Python, FastAPI, LangGraph, Claude (Anthropic) |
| [`Frontend/`](Frontend/) | React reviewer console (replaces the legacy Streamlit/Gradio UIs) | React 18, Vite, TypeScript, Tailwind, Clerk |

> Each subfolder is its own git repository with its own detailed README
> ([Backend/README.md](Backend/README.md), [Frontend/README.md](Frontend/README.md)).
> `Frontend/` is also referred to as `ap-exception-agent-ui-main`.

---

## Architecture

```
                 ┌─────────────────────────────┐
   CSV / JSON ──▶ │  Backend (FastAPI :8000)    │
   exception     │  ingest → classify (AI) →   │
   queue         │  severity → route (rules) → │
                 │  draft (AI) → prioritize →  │
                 │  persist → review           │
                 └──────────────┬──────────────┘
                                │  REST  /v1/runs, /v1/vendors, /v1/config …
                                ▼
                 ┌─────────────────────────────┐
   reviewer ───▶ │  Frontend (React :5173)     │
   (browser)     │  Clerk auth · dashboard ·   │
                 │  queue · classification ·   │
                 │  resolution · communications│
                 │  · priority · vendors ·     │
                 │  analytics · settings       │
                 └─────────────────────────────┘
```

**Design principle:** AI for ambiguity (classification, drafting), deterministic
code for certainty (severity, routing rules, prioritization, persistence) — so
decisions stay reproducible and auditable.

---

## Quickstart (local)

Two terminals.

**1. Backend** (runs in deterministic mock mode if no AI key is set):
```bash
cd Backend
pip install -e .
cp .env.example .env        # optional: add ANTHROPIC_API_KEY etc.
python -m uvicorn app.api.main:app --reload
# → http://localhost:8000  (docs at /docs)
```

**2. Frontend:**
```bash
cd Frontend
npm install
cp .env.example .env.local  # then paste your real Clerk publishable key
npm run dev
# → http://localhost:5173
```

The frontend talks to the backend via `VITE_API_BASE_URL` (default
`http://localhost:8000`); the backend's CORS already allows any localhost port.

## Quickstart (Docker)

```bash
cd Backend
export VITE_CLERK_PUBLISHABLE_KEY=pk_test_...   # PowerShell: $env:VITE_CLERK_PUBLISHABLE_KEY="pk_test_..."
docker compose up --build
# API → http://localhost:8000
# Web → http://localhost:8080  (nginx serves the SPA and proxies /v1 to the api)
```

---

## Configuration & secrets

| File | Commit to git? | Notes |
|---|---|---|
| `Backend/.env.example`, `Frontend/.env.example` |  Yes | Templates with placeholders only |
| `Backend/.env` |  **No** | AI keys, SMTP password, webhook URLs |
| `Frontend/.env`, `Frontend/.env.local` |  **No** | Clerk key + local overrides |

`.env` files are gitignored in both subprojects. **Never commit a real key** — a
secret pushed to GitHub is compromised even if later deleted (it persists in
history). Clerk *publishable* keys are public by design, but keeping them in
`.env.local` is still the convention.

Key environment variables:

| Var | Where | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | Backend | Enables Claude (else mock mode) |
| `COMMS_DRYRUN` | Backend | `true` = write artifacts instead of sending real email/Slack |
| `VITE_API_BASE_URL` | Frontend | Backend base URL |
| `VITE_CLERK_PUBLISHABLE_KEY` | Frontend | Clerk auth (Dashboard → API keys → React) |

---

## Authentication

The frontend uses **Clerk** to gate the UI (sign-in, route protection,
`<UserButton>`). Backend API authentication (verifying Clerk session tokens in
FastAPI) is **not yet implemented** — the API is currently open, so do not expose
`:8000` publicly until that is added.

---

## Testing

```bash
cd Backend  && pytest                 # backend unit tests
cd Frontend && npm test               # vitest (adapter unit tests)
```

CI: `Frontend/.github/workflows/ci.yml` runs tests + typecheck/build on push/PR.

---

## License

Proprietary — internal enterprise template.
