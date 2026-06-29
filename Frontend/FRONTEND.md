# AP Exception Handling Agent — Frontend Guide

A walkthrough of the React frontend: the end-to-end flow, what each page is for,
and the main elements on every screen. Written for designers, PMs, and engineers
onboarding to the app.

---

## 1. What this app is

An operator console for **Accounts Payable invoice-exception clearing**. A finance
controller uploads a queue of flagged invoices; an AI agent (FastAPI backend)
classifies each one, routes it through deterministic rules, and drafts the vendor
or internal communication. The human reviews, edits, approves, and sends — then the
payment can be released. Every decision is rule-traced and audit-logged.

The product metaphor is a **reconciliation ledger**: money sits *in suspension*
until each exception is cleared.

### Tech stack
| Layer | Choice |
|---|---|
| Framework | React 18 + TypeScript + Vite |
| Routing | react-router-dom v6 |
| Styling | Tailwind CSS + shadcn/ui (Radix primitives) |
| Animation | framer-motion |
| Charts | recharts |
| Auth | Clerk (`@clerk/react`) |
| Icons | lucide-react |

---

## 2. Architecture

### Entry & providers
`main.tsx` → `App.tsx`. Providers wrap everything (outermost → innermost):

```
ThemeProvider → PreferencesProvider → RunProvider → TooltipProvider → Router
```

- **ThemeProvider** (`useTheme`) — light / dark / system, persisted to `localStorage` (`ap-theme`).
- **PreferencesProvider** (`usePreferences`) — default landing view + table page size.
- **RunProvider** (`useRun`) — the single source of truth for the active run (see §4).

### Routing & layout
- `/login` — public landing page (renders the dashboard if already signed in).
- Every other route is wrapped in `AppLayout` and **lazy-loaded** (code-split) to keep the initial bundle small.
- `AppLayout` is a route guard: **signed-out users are bounced to `/login`**. Signed-in users get the persistent shell:

```
┌──────────┬─────────────────────────────────────────────┐
│          │  Header  (search · run switcher · alerts ·    │
│ Sidebar  │           theme · user)                       │
│  (nav +  ├─────────────────────────────────────────────┤
│  run     │                                               │
│  status) │   <Page>   (lazy-loaded route content)        │
│          │                                               │
└──────────┴─────────────────────────────────────────────┘
```

- `/` redirects to the user's preferred default view (Settings → Default View).

---

## 3. The run lifecycle (the core flow)

Everything in the app revolves around one **run** — one uploaded queue processed end to end.

```
  UPLOAD                    PROCESS (polled)                 REVIEW & CLEAR
 ┌────────┐   POST /v1/runs  ┌─────────────────┐  terminal  ┌──────────────────┐
 │ pick a │ ───────────────▶ │ PENDING/RUNNING  │ ─────────▶ │ AWAITING_REVIEW   │
 │ CSV /  │                  │ poll every 2s:   │            │  · edit drafts    │
 │ JSON   │                  │ ingest→classify→ │            │  · send (1 / all) │
 └────────┘                  │ resolve→draft→   │            │  · approve run    │
                             │ persist          │            └────────┬─────────┘
                             └─────────────────┘                      │ POST approve
                                      │ on terminal:                  ▼
                                      │ GET results + metrics +   COMPLETED
                                      │ audit, snapshot to        (or FAILED)
                                      ▼ localStorage
                             UI derives: exceptions,
                             communications, dashboard
                             stats, analytics, activities
```

1. **Upload** (`UploadPanel` on the Dashboard) → `POST /v1/runs` returns a `run_id` (status `PENDING`).
2. **Poll** `GET /v1/runs/{id}` every 2 s. The UI shows live progress (`current_node`, accumulating counts).
3. **Terminal status** (`AWAITING_REVIEW` / `COMPLETED` / `FAILED`) stops polling and triggers a fetch of **results + metrics + audit** from the backend. Persistence lives in the **backend DB run store** (durable across restarts); the only thing kept in `localStorage` is a pointer to the *active* run id, so a refresh re-opens the same run and re-fetches it from the DB.
4. Raw backend payloads are converted into UI shapes by `lib/adapters.ts` (→ `exceptions`, `communications`, `dashboardStats`, `analyticsData`, `activities`).
5. The operator **reviews drafts**, edits (`PATCH`), sends (`POST …/send` or `…/send_all`), and **approves** the run (`POST …/approve`).

Statuses: `PENDING` → `RUNNING` → `AWAITING_REVIEW` → `COMPLETED` (or `FAILED`).

---

## 4. State management

| Hook / module | Responsibility |
|---|---|
| **`useRun` / `RunProvider`** | Active run id/status, upload, polling, raw payloads (`results`, `metrics`, `priorityQueues`, `audit`), UI derivations (`exceptions`, `communications`, `dashboardStats`, `analyticsData`, `activities`), run **history sourced from the backend** (`GET /v1/runs`), and actions (`uploadFile`, `selectRun`, `approve`, `refresh`, `clearRun`, …). |
| **`usePreferences`** | `defaultView`, table `pageSize` — applied on save, persisted locally. |
| **`useTheme`** | light / dark / system. |
| `lib/api.ts` | Thin typed transport — one function per backend endpoint; attaches the Clerk bearer token. |
| `lib/adapters.ts` | Maps backend Pydantic shapes → UI `@/types`. |
| `lib/runHistory.ts` | Shared `RunHistoryEntry` type for the history picker (history itself comes from the backend DB via `useRun`). |
| `lib/format.ts` | Compact currency/number formatting (`$442.5K`, `$1.8M`) + full values for tooltips. |

**No global data fetching library** — `useRun` is the one store; pages just read from it.

---

## 5. Design system — "Auxilio" (corporate)

A clean enterprise-B2B identity aligned with [auxiliobits.com](https://www.auxiliobits.com/): white canvas, cool slate neutrals, one corporate blue. Defined as CSS variables in `index.css` + `tailwind.config.js`.

- **Corporate blue** (`primary`) `#2563EB` — the one saturated action color (Approve / Send / Review / "cleared") and the focus-ring color. Brand & section icons use it.
- **Ink slate** (`ink`) `#0F172A` — structure: sidebar rail, display numerals, chrome.
- **Canvas** — white with slate-100/200 surfaces & hairlines (light); deep-slate archive (dark).
- **Exception scale** — `overdue` (red, high/error), `pending` (amber, medium/warning), `settled` (green, low/success). Universal traffic-light semantics; all theme-aware tokens, so colors stay legible in both light and dark.
- **Type**: **Poppins** (everything — body/UI + display page titles & the balance numeral), **IBM Plex Mono** (all amounts, IDs, %s, traces — tabular numerals). Base size 14px.
- **Signature element**: the **Reconciliation Strip** (see Dashboard).

Icon convention used everywhere: **brand/section → `text-primary`; status → `settled`/`pending`/`overdue`; neutral → `text-muted-foreground`.**

---

## 6. Shared chrome

### Sidebar (`components/layout/Sidebar.tsx`)
The ink **rail**. Custom ledger logomark; collapsible. Nav items: Dashboard, Exception Queue, Priority Queue, Classification, Resolution Paths, Communications, Vendors, Analytics, Settings. Active row gets a verdigris margin-marker. Footer shows a **live run-status lamp** (verdigris = settled, ochre = processing, red = failed) with the current node + row count.

### Header (`components/layout/Header.tsx`)
- **Search** invoices/vendors (Enter → Queue filtered by `?q=`).
- **Run history switcher** — pick any past run; hydrates instantly from the local snapshot.
- **Notifications** — escalations needing review + quarantined rows.
- **Theme toggle** + **Clerk user menu**.

---

## 7. Page-by-page reference

> Pages that need run data render a shared **`EmptyRunState`** when there's no run / it's still processing / loading / errored.

### 🏠 Home / Login — `/login` (`LoginPage.tsx`)
- **Purpose**: public landing + sign-in. Renders the app if already authenticated. Fully **theme-aware** (light/dark) with a **theme toggle** in the top nav.
- **Main elements**: sticky top nav (Home / Exceptions / Audit Trail / Rules / Reports / Contact with scroll-spy + theme toggle) · hero ("Clear suspended AP cash — with a trail for every decision") · **live statement preview** card (suspended balance, 4 lifecycle stats, top-exceptions list) · pipeline strip (Ingest & classify → Route by rule → Draft → Review & clear) · scrolling sections per nav anchor · final CTA · **Contact section** (AISpace-style: blue gradient banner with an overlapping form card — first/last name, email, subject select, message, privacy-consent checkbox, full-width Send → opens a `mailto:`) · **newsletter** subscribe band · multi-column **footer** (brand + Product/Company/Support/Connect columns + Terms/Privacy bottom bar). Clerk **Sign in / Create account** (modal).
- **Data**: static marketing content; no run data.

### 📄 Legal — `/privacy`, `/terms` (`LegalPage.tsx`)
- **Purpose**: public Privacy Policy and Terms of Service. Theme-aware, content-first; linked from the home footer. Copy is a professional template to be reviewed by counsel.

### 📊 Dashboard — `/dashboard` (`DashboardPage.tsx`)
- **Purpose**: the "clearing desk" — your suspended balance and what each dollar is waiting on; the place you start a run.
- **Main elements**:
  - **Reconciliation Strip** (signature) — total suspended balance + a single clearing bar partitioned into **At risk / Escalated / Awaiting review / Cleared** by dollar value, with a stat-column legend.
  - **DashboardCards** — 4 operational tiles: Auto-resolvable, Escalations required, High severity, Resolution rate.
  - **UploadPanel** — drag-drop / browse CSV·JSON → "Clear this queue"; shows upload→process→done progress.
  - **ActivityTimeline** ("Processing trail") — agent's recorded steps; scrolls after ~4 events.
- **Data**: `exceptions`, `metrics`, `dashboardStats`, `activities` from `useRun`.

### 📋 Exception Queue — `/queue` (`QueuePage.tsx`)
- **Purpose**: the working list of every exception in the run.
- **Main elements**: **QuarantinedPanel** (collapsible banner for rows rejected at ingest) · **ExceptionTable** — searchable (Invoice ID / Vendor), filterable (Severity, Status), sortable columns (Amount, Days Outstanding, …), paginated (page size from preferences). Severity & status shown as ledger-stamp badges.
- **Data**: `exceptions`.

### 🗂️ Priority Queue — `/priority` (`PriorityPage.tsx`)
- **Purpose**: triage — what to clear first.
- **Main elements**: **PriorityKanban** — three columns HIGH / MEDIUM / LOW (overdue / pending / settled ink), each showing the top 5 exceptions as cards (invoice id, vendor, amount, severity, type) with a severity margin-accent.
- **Data**: `exceptions` (priority bucket comes from the backend priority queues).

### 🧠 AI Classification — `/classification` (`ClassificationPage.tsx`)
- **Purpose**: inspect the agent's classification for any single invoice.
- **Main elements**: invoice-ID lookup (search box → "View Classification") · **ClassificationPanel** — exception type, **confidence score** (progress bar), severity, root-cause hypothesis, and the AI reasoning summary. Plain-language, not a black box.
- **Data**: `results[].classification` for the typed invoice id.

### 🔀 Resolution Paths — `/resolution` (`ResolutionPage.tsx`)
- **Purpose**: the deterministic rules-engine catalogue — how exceptions get routed.
- **Main elements**: **ResolutionPathCards** — one card per path (Auto Approve, Escalate to Finance Controller, Request Missing PO, Hold for Investigation, Vendor Clarification Required) with its logic, assigned team, SLA, and automation level. Annotated with **live counts** of how many invoices in the current run hit each path.
- **Data**: static policy catalogue (`mockResolutionPaths`) overlaid with live `results[].resolution` counts.

### ✉️ Communications — `/communications` (`CommunicationsPage.tsx`)
- **Purpose**: review, edit, and send the agent's drafted messages.
- **Main elements**: **CommunicationTabs** grouped by channel (Vendor Email / Internal / Slack / Finance Note). Per draft: subject + body (editable), recipient override, **Copy / Edit / Send**, send-status badge, and **Send all** per channel. "Approve run" when status is `AWAITING_REVIEW`.
- **Data**: `communications`; actions hit the drafts endpoints.

### 🏢 Vendors — `/vendors` (`VendorsPage.tsx`)
- **Purpose**: per-vendor reliability dossier built up across runs.
- **Main elements**: a card per vendor — reliability score badge, invoices seen, amount processed, and exception/duplicate/escalation history.
- **Data**: `GET /v1/vendors` (independent of the active run).

### 📈 Analytics — `/analytics` (`AnalyticsPage.tsx`)
- **Purpose**: rates and distributions for the current run (the Dashboard shows absolute counts; Analytics shows the *rates*).
- **Main elements**: 4 KPI tiles (Auto-Resolution Rate, Escalation Rate, Avg Confidence, SLA At Risk) · **AnalyticsCharts** — Exceptions by Type (bar), Severity Distribution (pie), Exception Value by Type (bar), Resolution Status (pie), Top Vendors (bar). On-brand chart palette.
- **Data**: `analyticsData`, `metrics`, `dashboardStats`.

### ⚙️ Settings — `/settings` (`SettingsPage.tsx` → `SettingsPanel`)
- **Purpose**: connection health, read-only agent config, and UI preferences.
- **Main elements**: **Backend Connection** (API URL, health check, "Test connection") · **Agent Configuration** (read-only: environment, AI provider/models, dry-run vs live sending, channels, thresholds) · **Interface Preferences** (Theme, Default View, Table Page Size) with Save / Restore defaults.
- **Data**: `GET /v1/config`, `GET /healthz`, local preferences.

---

## 8. Backend API surface (consumed by `lib/api.ts`)

| Method & path | Used for |
|---|---|
| `POST /v1/runs` | Upload a queue, start a run |
| `GET /v1/runs` | Run history list |
| `GET /v1/runs/{id}` | Status + quarantine summary (polled) |
| `GET /v1/runs/{id}/results` | Per-invoice classification / resolution / draft |
| `GET /v1/runs/{id}/metrics` | Dashboard metrics + priority queues |
| `GET /v1/runs/{id}/audit` | Append-only audit log |
| `GET/PATCH /v1/runs/{id}/drafts/{invoice}` | Read / edit a draft |
| `POST …/drafts/{invoice}/send`, `…/drafts/send_all` | Send one / many |
| `POST /v1/runs/{id}/approve` | Mark the run COMPLETED |
| `GET /v1/vendors` | Vendor reliability profiles |
| `GET /v1/config`, `GET /healthz` | Settings page |

Base URL: `VITE_API_BASE_URL` (default `http://localhost:8000`). Auth: Clerk JWT sent as `Authorization: Bearer …` when signed in (ignored by the backend when `AUTH_ENABLED=false`).

---

## 9. Folder map

```
src/
├─ App.tsx, main.tsx          # entry, providers, routes
├─ index.css                  # design tokens (Ink & Verdigris) + utilities
├─ pages/                     # one file per route (see §7)
├─ components/
│  ├─ layout/                 # Sidebar, Header, ThemeToggle
│  ├─ signature/              # ReconciliationStrip (the signature element)
│  ├─ dashboard/              # DashboardCards, UploadPanel, ActivityTimeline
│  ├─ queue/                  # ExceptionTable, QuarantinedPanel
│  ├─ priority/               # PriorityKanban
│  ├─ classification/         # ClassificationPanel
│  ├─ resolution/             # ResolutionPathCards
│  ├─ communication/          # CommunicationTabs
│  ├─ analytics/              # AnalyticsCharts
│  ├─ settings/               # SettingsPanel
│  ├─ common/                 # EmptyRunState, ErrorBoundary
│  └─ ui/                     # shadcn primitives (button, card, badge, …)
├─ hooks/                     # useRun, usePreferences, useTheme
├─ lib/                       # api, adapters, runHistory, format, utils
├─ types/                     # UI type definitions
└─ data/                      # mockData (resolution-path catalogue)
```

---

*Generated as an onboarding reference. The run lifecycle in §3 and the per-page
elements in §7 are the two things to internalize first.*
