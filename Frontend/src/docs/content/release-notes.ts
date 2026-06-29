import { h1, h2, h3, p, ul, code, note, hr, type Block } from '../blocks';

const blocks: Block[] = [
  h1('Release Notes'),
  p('Versioned changelog for the AP Exception Agent. Newest first. We follow semantic versioning: **MAJOR.MINOR.PATCH**.'),
  note('**Policy versions** are separate from product versions. The shipped routing policy is versioned independently (current: `2026.05.1`) so rule changes are auditable on their own timeline.'),

  h2('v1.1.0 — 2026-06-16'),
  h3('Reliability & operations'),
  ul([
    '**Durable run queue** (opt-in): uploaded input is persisted and executed by a worker, so runs survive a restart, crashed runs are re-leased and retried, and work spreads across instances.',
    '**Real readiness probe** — `/readyz` now verifies the run store / database and returns `503` when a dependency is down.',
    '**Graceful shutdown** — in-flight runs are drained before the process exits.',
    '**Prometheus `/metrics`** — runs, AI token usage + estimated cost, and comms sends.',
  ]),
  h3('Safety'),
  ul([
    '**Per-domain daily send cap** is now enforced.',
    '**Vendor-master recipient lookup** — vendor emails resolve to the real AR contact; unknown vendors are refused, not mis-delivered.',
    '**Hardened production gate** — the API refuses to boot in `prod`/`staging` without auth, CORS allow-list, a durable store, and (for live comms) a domain allow-list.',
  ]),
  h3('Console'),
  ul([
    'Stale active-run pointers no longer surface a "Run not found" error on a fresh dashboard visit — the console clears them and returns to the upload state.',
    'Public **documentation site** (this site), accessible without login.',
  ]),

  h2('v1.0.0 — 2026-05-01'),
  h3('Initial release'),
  ul([
    'LangGraph pipeline: ingest → classify (AI) → severity → route (rules) → draft (AI) → prioritize → persist.',
    'Exception taxonomy, deterministic resolution policy (`v2026.05.1`), priority scoring.',
    'React console: Dashboard, Queue, Classification, Resolution, Communications, Priority, Vendors, Analytics, Settings.',
    'REST API, Clerk auth with tenant isolation, append-only audit log.',
    'Dry-run communications with email + Slack.',
  ]),

  hr(),

  h2('Release-note template'),
  p('Copy this for each release.'),
  code('text', `
## vMAJOR.MINOR.PATCH - YYYY-MM-DD

### Added
- <new capabilities>

### Changed
- <behavior changes; note any policy-version bump>

### Fixed
- <bug fixes>

### Security
- <security-relevant changes>

### Migration / upgrade notes
- <DB migrations to run, config changes required, breaking changes>
`),
  note('**Process:** every change ships with updated docs and, where schema changes, an Alembic migration verified up **and** down in CI.'),
];

export default blocks;
