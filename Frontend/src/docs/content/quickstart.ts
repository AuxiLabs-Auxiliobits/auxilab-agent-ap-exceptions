import { h1, h2, p, ul, ol, note, tip, warn, hr, type Block } from '../blocks';

const blocks: Block[] = [
  h1('Quickstart'),
  p('Run your first reconciliation in five steps. You will upload a queue, review an exception, read the dashboard, and clear an item — end to end.'),
  note('**Time:** ~5 minutes · **You need:** a sign-in to the console and a CSV/JSON exception queue (or use the [sample data](/docs/sample-data)).'),

  hr(),

  h2('Step 1 — Sign in and open the console'),
  p('Open the app and sign in. You land on the **Dashboard** — the clearing desk. If you have no runs yet, you see an empty state inviting you to upload.'),
  p('🖼️ *Screenshot placeholder: Dashboard empty state with the upload panel.*'),

  h2('Step 2 — Your first upload'),
  ol([
    'On the **Dashboard**, find **Upload exception queue**.',
    '**Drag & drop** a `.csv` or `.json` file, or click **Browse Files**.',
    'No file? Click **Download CSV template** for a ready-to-fill file, or use the [sample data](/docs/sample-data).',
  ]),
  p('The upload returns immediately and the run begins processing in the background. The status moves through `PENDING → RUNNING → AWAITING_REVIEW`.'),
  p('**What happens on upload:** rows are validated, each exception is classified, severity is set, the invoice is routed, communications are drafted, and the priority queue is built. Malformed rows are **quarantined**, not dropped. See [File Import](/docs/file-import).'),

  h2('Step 3 — Your first exception review'),
  ol([
    'Go to **Classification** to see every invoice with its detected exception type, confidence score, and rationale.',
    'Open one exception to see the type, a **confidence** bar, the **rationale** in plain language, and the **severity** and **resolution path** the rules chose.',
  ]),
  tip('Low-confidence items (below 60%) are automatically routed to **manual review** — look for those first.'),

  h2('Step 4 — Your first dashboard review'),
  p('Return to the **Dashboard** and read the clearing desk:'),
  ul([
    '**Suspended balance** — total exception value, partitioned by lifecycle (at-risk, escalated, awaiting, cleared).',
    '**Breakdowns** — by exception type, severity, and resolution path.',
    '**Top actionable** — the highest-priority items to clear first.',
  ]),
  p('Then open **Analytics** for trends and **Vendors** for per-vendor reliability. See [Dashboards](/docs/dashboards) for every metric and calculation.'),

  h2('Step 5 — Your first resolution workflow'),
  ol([
    'Go to **Communications**. Each invoice that requires an outbound message has a **draft** — vendor email, internal email, Slack, or finance note.',
    '**Read and edit** the draft. The wording is AI-generated; the recipient and template are deterministic.',
    '**Send** the draft (or **Send all**). By default the system runs in **dry-run** mode — it writes a preview file instead of emailing a real vendor, so you can verify safely.',
    'When the run is reviewed, click **Approve** to mark it `COMPLETED`.',
  ]),
  warn('**Safety:** the agent never sends on its own. Live sending requires turning off dry-run **and** configuring a recipient-domain allowlist. See [Administrator Guide](/docs/admin-guide).'),

  hr(),

  h2('What’s next'),
  ul([
    'Understand the taxonomy → [Exception Types](/docs/exception-types)',
    'Understand routing → [Resolution Paths](/docs/resolution-paths)',
    'Configure for production → [Administrator Guide](/docs/admin-guide)',
  ]),
];

export default blocks;
