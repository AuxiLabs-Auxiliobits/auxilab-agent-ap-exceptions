/**
 * Typed client for the AP Exception Handling Agent FastAPI backend.
 *
 * Every function maps 1:1 to an endpoint documented in the backend README.
 * Response shapes mirror the Pydantic schemas in `Backend/app/schemas`.
 * Adapting these backend shapes into the UI's `@/types` happens in
 * `src/lib/adapters.ts` — keep this file a thin transport layer.
 */

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ??
  'http://localhost:8000';

export const DEFAULT_TENANT_ID: string =
  (import.meta.env.VITE_TENANT_ID as string | undefined) ?? 'default';

// ---------------------------------------------------------------------------
// Backend response types (subset of fields the UI consumes)
// ---------------------------------------------------------------------------

export type RunStatus =
  | 'PENDING'
  | 'RUNNING'
  | 'AWAITING_REVIEW'
  | 'COMPLETED'
  | 'FAILED';

export const TERMINAL_STATUSES: RunStatus[] = [
  'AWAITING_REVIEW',
  'COMPLETED',
  'FAILED',
];

export interface RunSummary {
  run_id: string;
  tenant_id: string;
  status: RunStatus;
  created_at: string;
  rows_accepted: number;
  rows_quarantined: number;
  current_node?: string | null;
}

export interface QuarantinedRow {
  row_index: number;
  raw: Record<string, unknown>;
  reason_code: string;
  reason: string;
}

/** A pipeline-node failure, as recorded in the run state (app/schemas/run.py). */
export interface NodeErrorDetail {
  node_name: string;
  error_class: string;
  message: string;
  attempt?: number;
  is_retryable?: boolean;
  timestamp?: string;
}

export interface RunDetail {
  run_id: string;
  tenant_id: string;
  status: RunStatus;
  current_node?: string | null;
  rows_accepted: number;
  rows_quarantined: number;
  quarantined: QuarantinedRow[];
  errors: NodeErrorDetail[];
}

export type BackendExceptionType =
  | 'Price Variance'
  | 'Quantity Mismatch'
  | 'Missing PO'
  | 'Duplicate'
  | 'Unapproved Vendor'
  | 'GRN Not Received'
  | 'Other';

export type BackendSeverity = 'HIGH' | 'MEDIUM' | 'LOW';

export type ResolutionPathEnum =
  | 'AUTO_APPROVE'
  | 'REQUEST_PO'
  | 'ESCALATE_CONTROLLER'
  | 'HOLD_INVESTIGATION'
  | 'VENDOR_VALIDATION_REVIEW'
  | 'REQUEST_GRN'
  | 'MANUAL_REVIEW';

export type CommChannel =
  | 'vendor_email'
  | 'internal_email'
  | 'slack'
  | 'finance_note';

export type SendStatus =
  | 'draft'
  | 'dryrun'
  | 'sent'
  | 'failed'
  | 'skipped';

export interface ExceptionRow {
  invoice_id: string;
  vendor_name: string;
  invoice_amount: string | number;
  po_number?: string | null;
  exception_type: string;
  exception_description: string;
  days_outstanding: number;
  approver_assigned?: string | null;
  /** Optional per-invoice SLA window in days from the CSV; overrides the rule SLA. */
  sla_days?: number | null;
}

export interface ClassificationResult {
  invoice_id: string;
  primary_exception_type: BackendExceptionType;
  root_cause: string;
  severity_ai_suggested: BackendSeverity;
  severity: BackendSeverity;
  confidence_score: number;
  rationale: string;
  model_id: string;
  prompt_version: string;
}

export interface ResolutionDecision {
  invoice_id: string;
  resolution_path: ResolutionPathEnum;
  rule_id: string;
  rule_version: string;
  rule_trace: string[];
  requires_communication: boolean;
  sla_hours: number;
}

export interface CommunicationDraft {
  invoice_id: string;
  channel: CommChannel;
  recipient_hint: string;
  subject?: string | null;
  body: string;
  tone: string;
  template_id: string;
  model_id: string;
  is_edited_by_human: boolean;
  recipient?: string | null;
  send_status: SendStatus;
  send_provider?: string | null;
  send_message_id?: string | null;
  sent_at?: string | null;
  send_error?: string | null;
}

export interface ResultItem {
  invoice_id: string;
  row: ExceptionRow;
  classification: ClassificationResult | null;
  resolution: ResolutionDecision | null;
  draft: CommunicationDraft | null;
}

export interface ResultsResponse {
  run_id: string;
  count: number;
  results: ResultItem[];
}

export interface PriorityEntry {
  invoice_id: string;
  priority_score: number;
  bucket: 'HIGH' | 'MEDIUM' | 'LOW';
  drivers: string[];
}

export interface PriorityQueues {
  high: PriorityEntry[];
  medium: PriorityEntry[];
  low: PriorityEntry[];
}

export interface DashboardMetrics {
  total_exceptions: number;
  auto_resolvable_count: number;
  escalations_required: number;
  total_exception_value: string | number;
  breakdown_by_type: Record<string, number>;
  breakdown_by_severity: Record<string, number>;
  breakdown_by_resolution_path: Record<string, number>;
  top_5_actionable: PriorityEntry[];
  sla_at_risk_count: number;
  average_confidence: number;
}

export interface MetricsResponse {
  run_id: string;
  metrics: DashboardMetrics | null;
  priority_queues: PriorityQueues | null;
}

export interface AuditEvent {
  event_id: string;
  run_id: string;
  invoice_id?: string | null;
  node_name: string;
  event_type: string;
  timestamp: string;
  actor: string;
  metadata: Record<string, unknown>;
}

export interface AuditResponse {
  run_id: string;
  events: AuditEvent[];
}

/** One prior appearance of an invoice in another run. */
export interface DuplicateOccurrence {
  run_id: string;
  created_at: string;
  invoice_amount: string;
  vendor_name: string;
  /** True when the prior amount equals this run's amount (a likely exact double-pay). */
  amount_matches: boolean;
}

export interface DuplicateHit {
  invoice_id: string;
  vendor_name: string;
  invoice_amount: string;
  occurrences: DuplicateOccurrence[];
}

export interface DuplicatesResponse {
  run_id: string;
  /** Invoices in this run that were checked. */
  checked: number;
  /** How many other runs were scanned. */
  runs_scanned: number;
  duplicate_count: number;
  duplicates: DuplicateHit[];
}

export interface AskResult {
  run_id: string;
  question: string;
  answer: string;
  cited_invoice_ids: string[];
  intent: string;
}

export type CaseStatus = 'OPEN' | 'IN_PROGRESS' | 'RESOLVED' | 'WONT_FIX';

export interface Case {
  invoice_id: string;
  status: CaseStatus;
  note?: string | null;
  updated_at?: string | null;
  updated_by?: string | null;
}

export interface CasesResponse {
  run_id: string;
  /** invoice_id -> case; invoices with no entry are treated as OPEN. */
  cases: Record<string, Case>;
}

export interface TrendRun {
  run_id: string;
  created_at: string | null;
  status: string | null;
  total_exceptions: number;
  total_value: string;
  auto_resolvable: number;
  escalations: number;
  high_severity: number;
  avg_confidence: number;
  sla_at_risk: number;
  resolved: number;
  closed: number;
  /** Mean hours from run start to case closure, or null if none closed yet. */
  avg_cycle_hours: number | null;
}

export interface TrendTotals {
  runs: number;
  total_exceptions: number;
  total_value: string;
  resolved: number;
  closed: number;
  resolution_rate: number;
  auto_resolution_rate: number;
  avg_confidence: number;
  avg_cycle_hours: number | null;
}

export interface TrendsResponse {
  runs: TrendRun[];
  totals: TrendTotals;
}

export interface DigestResult {
  run_id: string;
  notification: {
    status: 'sent' | 'dryrun' | 'skipped';
    recipient?: string;
    subject?: string;
    message_id?: string;
    reason?: string;
  };
  summary: {
    total_open: number;
    high_waiting: number;
    breached: number;
    due_soon: number;
    in_progress: number;
    resolved: number;
    needs_follow_up: number;
  };
}

export interface RuleSimChange {
  invoice_id: string;
  vendor_name: string;
  invoice_amount: string;
  exception_type: string;
  from: string;
  to: string;
}

export interface RuleSimulation {
  run_id: string;
  candidate_version: string;
  current_version: string;
  total: number;
  changed_count: number;
  current_distribution: Record<string, number>;
  simulated_distribution: Record<string, number>;
  changes: RuleSimChange[];
}

export interface RunListResponse {
  runs: RunSummary[];
  total: number;
}

export interface VendorProfile {
  vendor_name: string;
  total_invoices_seen: number;
  total_amount_processed: string | number;
  exception_type_counts: Record<string, number>;
  resolution_path_counts: Record<string, number>;
  average_days_outstanding: number;
  average_confidence: number;
  duplicate_count: number;
  auto_approved_count: number;
  escalated_count: number;
  missing_po_count: number;
  unapproved_vendor_count: number;
  first_seen_at: string;
  last_seen_at: string;
  reliability_score: number;
}

export interface VendorListResponse {
  profiles: VendorProfile[];
  total_vendors: number;
}

/** Per-tenant vendor directory entry (vendor → AR email) used for routing. */
export interface VendorContact {
  vendor_name: string;
  email: string;
  contact_name: string | null;
  updated_at: string | null;
  updated_by: string | null;
}

export interface VendorContactsResponse {
  contacts: VendorContact[];
}

export interface VendorContactInput {
  vendor_name: string;
  email: string;
  contact_name?: string | null;
}

export interface BackendConfig {
  app_name: string;
  environment: string;
  ai: {
    active_provider: string;
    classify_model: string;
    draft_model: string;
    mock_mode: boolean;
  };
  comms: {
    dryrun: boolean;
    email_configured: boolean;
    slack_configured: boolean;
    html_enabled: boolean;
    per_domain_daily_cap: number;
  };
  severity_thresholds: {
    high_amount: number;
    high_days: number;
    medium_amount_min: number;
  };
  priority: {
    weights: {
      amount: number;
      age: number;
      severity: number;
      path: number;
      confidence: number;
    };
    high_threshold: number;
    medium_threshold: number;
  };
}

export interface SendResult {
  invoice_id: string;
  status: SendStatus;
  provider: string;
  message_id: string | null;
  recipient: string | null;
  sent_at: string | null;
  error_message: string | null;
}

/** RBAC permission strings — mirror app/api/roles.py exactly. */
export type Permission =
  | 'run:read'
  | 'run:create'
  | 'draft:edit'
  | 'comms:send'
  | 'run:approve'
  | 'config:write';

export type Role =
  | 'admin'
  | 'manager'
  | 'clerk'
  | 'controller'
  | 'auditor'
  | 'procurement';

/** GET /v1/me — the authenticated caller's identity, role, and permissions. */
export interface Me {
  subject: string;
  tenant_id: string;
  role: Role;
  permissions: Permission[];
}

/** A Slack Block Kit block (loosely typed — we only read a few shapes). */
export interface SlackBlock {
  type: string;
  text?: { type: string; text: string };
  fields?: { type: string; text: string }[];
  elements?: { type: string; text: string }[];
}

/** Rendered preview of an outbound comm (both representations). */
export interface CommsPreview {
  channel: CommChannel;
  subject: string | null;
  email: { html: string; text: string };
  slack: { blocks: SlackBlock[]; text: string };
}

/** Per-org integration (BYOK) — Phase 2a. */
export type IntegrationKind = 'ai_anthropic' | 'ai_gemini' | 'ai_azure' | 'email' | 'slack' | 'branding';

export interface IntegrationStatus {
  kind: IntegrationKind;
  configured: boolean;
  meta: Record<string, string>;
  updated_at: string | null;
  updated_by: string | null;
}

export interface IntegrationsResponse {
  tenant_id: string;
  per_org_config_enabled: boolean;
  enc_key_configured: boolean;
  /** Whether the platform has registered a Google OAuth app (GOOGLE_OAUTH_*). */
  google_oauth_configured: boolean;
  /** Whether the platform has registered a Slack OAuth app (SLACK_CLIENT_*). */
  slack_oauth_configured: boolean;
  writable_kinds: string[];
  integrations: IntegrationStatus[];
}

export interface RulesResponse {
  tenant_id: string;
  is_custom: boolean;
  /** The effective rulebook (the org's custom one if set, else the default). */
  policy: unknown;
  /** The platform default rulebook — a baseline to revert to / diff against. */
  default_policy: unknown;
}

export interface RulesValidateResult {
  ok: boolean;
  version?: string;
  rules?: number;
  error?: string;
}

export interface RuleOverride {
  rule_id: string;
  count: number;
  /** new resolution path → how many times humans re-routed this rule to it. */
  to_paths: Record<string, number>;
}

export interface RuleOverridesReport {
  total_overrides: number;
  runs_scanned: number;
  rules: RuleOverride[];
}

export interface IntegrationInput {
  secret?: string;
  // AI
  classify_model?: string;
  draft_model?: string;
  // Azure
  endpoint?: string;
  deployment?: string;
  api_version?: string;
  // Email (SMTP)
  smtp_host?: string;
  smtp_port?: string;
  from_address?: string;
  dryrun?: boolean;
  // Branding
  signature_name?: string;
  signature_team?: string;
  signature_company?: string;
  signature_disclaimer?: string;
  disclose_ai?: boolean;
  brand_color?: string;
  logo_url?: string;
}

export interface IntegrationTestResult {
  kind: string;
  ok: boolean;
  active_provider: string;
  classify_model: string;
  draft_model: string;
  detail: string;
}

/** Body for POST /v1/preview/comms — all fields optional (server has defaults). */
export interface CommsPreviewInput {
  channel?: CommChannel;
  invoice_id?: string;
  subject?: string | null;
  body?: string;
  tone?: string;
  vendor_name?: string | null;
  invoice_amount?: number | null;
  severity?: string | null;
  exception_type?: string | null;
  resolution_path?: string | null;
  sla_hours?: number | null;
  days_outstanding?: number | null;
  signature_name?: string | null;
  signature_team?: string | null;
  signature_company?: string | null;
  signature_disclaimer?: string | null;
  disclose_ai_assistance?: boolean | null;
  brand_color?: string | null;
  logo_url?: string | null;
}

/** Public landing-page contact form. */
export interface ContactInput {
  name?: string;
  email?: string;
  subject?: string;
  message: string;
  company_website?: string; // honeypot
}

// ---------------------------------------------------------------------------
// Transport
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

// Network hardening knobs. A request can hang forever without a timeout, and a
// single transient failure (502/503/504, network blip) shouldn't surface as a
// hard error when the call is safe to repeat.
const REQUEST_TIMEOUT_MS = 30_000;
const MAX_RETRIES = 2; // total attempts = MAX_RETRIES + 1
const RETRYABLE_STATUSES = new Set([502, 503, 504]);

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function isIdempotent(method: string | undefined): boolean {
  const m = (method ?? 'GET').toUpperCase();
  return m === 'GET' || m === 'HEAD';
}

/**
 * Get the current Clerk session token (if signed in). Clerk exposes the active
 * session on `window.Clerk`; reading it here lets this plain module attach
 * `Authorization: Bearer <jwt>` without being a React hook. Harmless when the
 * backend has AUTH_ENABLED=false (the header is simply ignored).
 */
interface ClerkLike {
  loaded?: boolean;
  session?: { getToken: () => Promise<string | null> } | null;
}

function getClerk(): ClerkLike | undefined {
  return (window as unknown as { Clerk?: ClerkLike }).Clerk;
}

async function getAuthToken(): Promise<string | null> {
  try {
    // On a page refresh, Clerk loads asynchronously — `window.Clerk` may not
    // exist yet (or `loaded` is still false) when the first requests fire.
    // Wait briefly so we never send an authed request without a bearer token
    // (which the backend rejects with 401 "Missing bearer token").
    const deadline = Date.now() + 5000;
    let clerk = getClerk();
    while ((!clerk || !clerk.loaded) && Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 50));
      clerk = getClerk();
    }
    return clerk?.session ? await clerk.session.getToken() : null;
  } catch {
    return null;
  }
}

async function request<T>(
  path: string,
  init?: RequestInit,
  opts?: { timeoutMs?: number },
): Promise<T> {
  const retryable = isIdempotent(init?.method);
  const timeoutMs = opts?.timeoutMs ?? REQUEST_TIMEOUT_MS;
  let lastErr: unknown;

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    // Fetch a fresh token each attempt so a token that expired mid-retry is
    // replaced. AbortController bounds each attempt so a hung backend can't
    // wedge the UI forever.
    const token = await getAuthToken();
    const authHeader: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    let res: Response;
    try {
      // Spread `init` FIRST, then set the merged headers LAST — otherwise an
      // `init.headers` (e.g. Content-Type on POST /send) overwrites the whole
      // headers object and drops Authorization, causing a 401 on writes.
      res = await fetch(`${API_BASE_URL}${path}`, {
        ...init,
        signal: controller.signal,
        headers: {
          Accept: 'application/json',
          ...(init?.headers as Record<string, string> | undefined),
          ...authHeader,
        },
      });
    } catch (cause) {
      clearTimeout(timer);
      const aborted = cause instanceof DOMException && cause.name === 'AbortError';
      lastErr = new ApiError(
        0,
        aborted
          ? `Request to ${path} timed out after ${timeoutMs / 1000}s.`
          : `Cannot reach the backend at ${API_BASE_URL}. Is it running? (${String(cause)})`,
      );
      // Retry idempotent requests on network/timeout failures.
      if (retryable && attempt < MAX_RETRIES) {
        await sleep(300 * 2 ** attempt + Math.random() * 200);
        continue;
      }
      throw lastErr;
    } finally {
      clearTimeout(timer);
    }

    if (!res.ok) {
      // Retry idempotent requests on transient upstream errors.
      if (retryable && RETRYABLE_STATUSES.has(res.status) && attempt < MAX_RETRIES) {
        await sleep(300 * 2 ** attempt + Math.random() * 200);
        continue;
      }
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = body?.detail ?? JSON.stringify(body);
      } catch {
        /* non-JSON error body — keep statusText */
      }
      // A 401 almost always means the Clerk session lapsed — make that actionable.
      if (res.status === 401) {
        throw new ApiError(401, 'Your session has expired. Please sign in again.');
      }
      throw new ApiError(res.status, `${res.status} ${detail}`);
    }

    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  // Unreachable in practice (the loop always returns or throws), but satisfies
  // the type checker and guards against a logic slip.
  throw lastErr ?? new ApiError(0, `Request to ${path} failed.`);
}

/**
 * Fetch a file with the Clerk bearer token attached and trigger a browser save
 * dialog. A plain <a href> download can't send the Authorization header, so
 * authenticated downloads (template, rejection report) must go through fetch.
 */
async function authedDownload(path: string, filename: string): Promise<void> {
  const token = await getAuthToken();
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new ApiError(res.status, `Download failed (${res.status})`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export interface UploadFormatColumn {
  name: string;
  required: boolean;
  type: string;
  description: string;
}
export interface UploadFormat {
  accepted_file_types: string[];
  max_size_mb: number;
  delimiters_supported: string[];
  columns: UploadFormatColumn[];
  notes: string[];
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

export const api = {
  /** POST /v1/runs — upload a CSV/JSON queue and schedule a run. */
  async createRun(file: File, tenantId: string = DEFAULT_TENANT_ID): Promise<RunSummary> {
    const form = new FormData();
    form.append('file', file);
    form.append('tenant_id', tenantId);
    return request<RunSummary>('/v1/runs', { method: 'POST', body: form });
  },

  /** GET /v1/runs — list all runs (newest first) for the history picker. */
  listRuns(): Promise<RunListResponse> {
    return request<RunListResponse>('/v1/runs');
  },

  /** GET /v1/runs/{id} — run status + quarantine/error summary. */
  getRun(runId: string): Promise<RunDetail> {
    return request<RunDetail>(`/v1/runs/${runId}`);
  },

  /** GET /v1/runs/{id}/results — per-invoice classification/resolution/draft. */
  getResults(runId: string): Promise<ResultsResponse> {
    return request<ResultsResponse>(`/v1/runs/${runId}/results`);
  },

  /** GET /v1/runs/{id}/metrics — dashboard metrics + priority queues. */
  getMetrics(runId: string): Promise<MetricsResponse> {
    return request<MetricsResponse>(`/v1/runs/${runId}/metrics`);
  },

  /** GET /v1/runs/{id}/audit — append-only audit log. */
  getAudit(runId: string): Promise<AuditResponse> {
    return request<AuditResponse>(`/v1/runs/${runId}/audit`);
  },

  /** GET /v1/runs/{id}/duplicates — invoices also seen in the tenant's other runs. */
  getDuplicates(runId: string): Promise<DuplicatesResponse> {
    return request<DuplicatesResponse>(`/v1/runs/${runId}/duplicates`);
  },

  /** POST /v1/runs/{id}/ask — read-only grounded Q&A over the run's data. */
  askDesk(runId: string, question: string): Promise<AskResult> {
    return request<AskResult>(`/v1/runs/${runId}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });
  },

  /** GET /v1/runs/{id}/cases — per-invoice resolution lifecycle. */
  getCases(runId: string): Promise<CasesResponse> {
    return request<CasesResponse>(`/v1/runs/${runId}/cases`);
  },

  /** GET /v1/analytics/trends — cross-run aggregates + totals for the tenant. */
  getTrends(): Promise<TrendsResponse> {
    return request<TrendsResponse>('/v1/analytics/trends');
  },

  /** POST /v1/runs/{id}/notify — email the AP team an SLA + case digest (comms:send). */
  sendDigest(runId: string): Promise<DigestResult> {
    return request<DigestResult>(`/v1/runs/${runId}/notify`, { method: 'POST' });
  },

  /** PATCH /v1/runs/{id}/cases/{invoice} — advance a case (draft:edit). */
  updateCase(
    runId: string,
    invoiceId: string,
    status: CaseStatus,
    note?: string,
  ): Promise<{ status: string; case: Case }> {
    return request(`/v1/runs/${runId}/cases/${invoiceId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status, note }),
    });
  },

  /** GET /v1/runs/{id}/drafts/{invoice_id} — one draft. */
  getDraft(runId: string, invoiceId: string): Promise<CommunicationDraft> {
    return request<CommunicationDraft>(`/v1/runs/${runId}/drafts/${invoiceId}`);
  },

  /** PATCH /v1/runs/{id}/drafts/{invoice_id} — edit a draft body/subject. */
  patchDraft(
    runId: string,
    invoiceId: string,
    payload: { body: string; subject?: string | null },
  ): Promise<{ status: string }> {
    return request(`/v1/runs/${runId}/drafts/${invoiceId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  /** POST /v1/runs/{id}/approve — mark the run COMPLETED. */
  approveRun(runId: string): Promise<{ run_id: string; status: string }> {
    return request(`/v1/runs/${runId}/approve`, { method: 'POST' });
  },

  /**
   * POST /v1/runs/{id}/drafts/{invoice_id}/send — send one draft.
   *
   * Pass `resend: true` for an explicit operator resend of an already-sent
   * draft: the backend re-resolves the recipient from the current vendor
   * directory (so an edited vendor email is used) instead of replaying the
   * original address. A plain send stays idempotent.
   */
  sendDraft(
    runId: string,
    invoiceId: string,
    recipientOverride?: string,
    resend?: boolean,
  ): Promise<SendResult> {
    const payload: { recipient_override?: string; resend?: boolean } = {};
    if (recipientOverride) payload.recipient_override = recipientOverride;
    if (resend) payload.resend = true;
    return request(`/v1/runs/${runId}/drafts/${invoiceId}/send`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  /**
   * POST /v1/runs/{id}/drafts/send_all — bulk-send selected drafts.
   *
   * Send in modest batches (see SEND_ALL_BATCH_SIZE) and give each batch a
   * longer timeout, since one batch can dispatch several emails (each its own
   * SMTP round-trip) and would otherwise trip the default 30s abort. Sends are
   * idempotent on the backend, so an interrupted bulk send resumes on re-click.
   */
  sendAll(
    runId: string,
    invoiceIds: string[],
  ): Promise<{ run_id: string; dryrun: boolean; results: SendResult[]; summary: Record<string, number> }> {
    return request(
      `/v1/runs/${runId}/drafts/send_all`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ invoice_ids: invoiceIds }),
      },
      { timeoutMs: 120_000 },
    );
  },

  /** GET /v1/vendors — vendor reliability profiles. */
  listVendors(): Promise<VendorListResponse> {
    return request<VendorListResponse>('/v1/vendors');
  },

  /** GET /v1/vendor-contacts — this org's vendor → email directory. */
  listVendorContacts(): Promise<VendorContactsResponse> {
    return request<VendorContactsResponse>('/v1/vendor-contacts');
  },

  /** PUT /v1/vendor-contacts — create/update a vendor's email (admin). */
  putVendorContact(
    body: VendorContactInput,
  ): Promise<{ ok: boolean; vendor_name: string; email: string }> {
    return request('/v1/vendor-contacts', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  },

  /** DELETE /v1/vendor-contacts — remove a vendor's email (admin). */
  deleteVendorContact(vendorName: string): Promise<{ deleted: boolean; vendor_name: string }> {
    return request('/v1/vendor-contacts', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ vendor_name: vendorName }),
    });
  },

  /** GET /v1/config — read-only, non-secret runtime configuration. */
  getConfig(): Promise<BackendConfig> {
    return request<BackendConfig>('/v1/config');
  },

  /** GET /v1/me — the caller's role + effective permissions (RBAC). */
  me(): Promise<Me> {
    return request<Me>('/v1/me');
  },

  /** POST /v1/preview/comms — render arbitrary content + branding overrides (no send). */
  previewComms(payload: CommsPreviewInput = {}): Promise<CommsPreview> {
    return request<CommsPreview>('/v1/preview/comms', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  /** GET /v1/runs/{id}/drafts/{invoice_id}/preview — render a real draft (no send). */
  previewDraft(runId: string, invoiceId: string): Promise<CommsPreview> {
    return request<CommsPreview>(`/v1/runs/${runId}/drafts/${invoiceId}/preview`);
  },

  /** GET /v1/org/integrations — per-org integration status (admin; no secrets). */
  listIntegrations(): Promise<IntegrationsResponse> {
    return request<IntegrationsResponse>('/v1/org/integrations');
  },

  /** PUT /v1/org/integrations/{kind} — set/replace a provider's key + meta (admin). */
  putIntegration(kind: IntegrationKind, body: IntegrationInput): Promise<IntegrationsResponse> {
    return request<IntegrationsResponse>(`/v1/org/integrations/${kind}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  },

  /** DELETE /v1/org/integrations/{kind} — remove a provider's config (admin). */
  deleteIntegration(kind: IntegrationKind): Promise<{ tenant_id: string; removed: string }> {
    return request(`/v1/org/integrations/${kind}`, { method: 'DELETE' });
  },

  /** POST /v1/org/integrations/{kind}/test — validate the stored provider (admin). */
  testIntegration(kind: IntegrationKind): Promise<IntegrationTestResult> {
    return request<IntegrationTestResult>(`/v1/org/integrations/${kind}/test`, { method: 'POST' });
  },

  /** GET /v1/integrations/{provider}/connect — start OAuth; returns the consent URL. */
  oauthConnect(provider: 'google' | 'slack'): Promise<{ auth_url: string }> {
    return request<{ auth_url: string }>(`/v1/integrations/${provider}/connect`);
  },

  /** POST /v1/integrations/{provider}/callback — finish OAuth with the returned code. */
  oauthCallback(
    provider: 'google' | 'slack',
    code: string,
    state: string,
  ): Promise<{ status: string; email?: string; team?: string }> {
    return request(`/v1/integrations/${provider}/callback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, state }),
    });
  },

  /** GET /v1/org/rules — the org's effective rulebook + the default baseline (admin). */
  getRules(): Promise<RulesResponse> {
    return request<RulesResponse>('/v1/org/rules');
  },

  /** PUT /v1/org/rules — validate + store this org's rulebook (admin). */
  putRules(policy: unknown): Promise<{ tenant_id: string; is_custom: boolean; version: string }> {
    return request('/v1/org/rules', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ policy }),
    });
  },

  /** DELETE /v1/org/rules — revert to the platform default (admin). */
  deleteRules(): Promise<{ tenant_id: string; reverted_to_default: boolean; had_custom: boolean }> {
    return request('/v1/org/rules', { method: 'DELETE' });
  },

  /** POST /v1/org/rules/validate — validate a candidate policy without saving (admin). */
  validateRules(policy: unknown): Promise<RulesValidateResult> {
    return request<RulesValidateResult>('/v1/org/rules/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ policy }),
    });
  },

  /** POST /v1/org/rules/simulate — what-if: re-route a run under a candidate policy (admin). */
  simulateRules(runId: string, policy: unknown): Promise<RuleSimulation> {
    return request<RuleSimulation>('/v1/org/rules/simulate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_id: runId, policy }),
    });
  },

  /** GET /v1/org/rules/overrides — most-overridden rules (rulebook tuning signal, admin). */
  getRuleOverrides(): Promise<RuleOverridesReport> {
    return request<RuleOverridesReport>('/v1/org/rules/overrides');
  },

  /** POST /v1/runs/{runId}/resolutions/{invoiceId}/override — human reroute (recorded). */
  overrideResolution(
    runId: string,
    invoiceId: string,
    resolutionPath: ResolutionPathEnum,
    reason: string,
  ): Promise<{ status: string; resolution_path: string; original_path?: string; original_rule_id?: string }> {
    return request(`/v1/runs/${runId}/resolutions/${invoiceId}/override`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resolution_path: resolutionPath, reason }),
    });
  },

  /** GET /healthz — liveness probe. */
  health(): Promise<{ status: string }> {
    return request('/healthz');
  },

  /** POST /v1/contact — public landing-page contact form. */
  submitContact(payload: ContactInput): Promise<{ status: string; delivered?: boolean }> {
    return request('/v1/contact', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  /** POST /v1/subscribe — public newsletter signup. */
  subscribe(email: string, companyWebsite = ''): Promise<{ status: string; delivered?: boolean }> {
    return request('/v1/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, company_website: companyWebsite }),
    });
  },

  // ---- Newsletter admin (platform-operator; token-gated via X-Newsletter-Token) ----
  /** GET /v1/newsletter/stats — subscriber counts. */
  newsletterStats(token: string): Promise<{ active: number; total: number; unsubscribed: number }> {
    return request('/v1/newsletter/stats', { headers: { 'X-Newsletter-Token': token } });
  },

  /** POST /v1/newsletter/preview — render the email HTML (no send). */
  newsletterPreview(token: string, subject: string, body: string): Promise<{ html: string }> {
    return request('/v1/newsletter/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Newsletter-Token': token },
      body: JSON.stringify({ subject, body }),
    });
  },

  /** POST /v1/newsletter — send to all active subscribers (or dry-run). */
  sendNewsletter(
    token: string,
    subject: string,
    body: string,
    dryRun: boolean,
  ): Promise<{ recipients: number; sent: number; failed: number; dry_run?: boolean; capped_out?: number }> {
    return request('/v1/newsletter', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Newsletter-Token': token },
      body: JSON.stringify({ subject, body, dry_run: dryRun }),
    });
  },

  /** GET /v1/upload/format — accepted columns, types, file types, aliases. */
  getUploadFormat(): Promise<UploadFormat> {
    return request<UploadFormat>('/v1/upload/format');
  },

  /** GET /v1/upload/template.csv — download the ready-to-fill CSV template. */
  downloadTemplate(): Promise<void> {
    return authedDownload('/v1/upload/template.csv', 'ap_exception_template.csv');
  },

  /** GET /v1/runs/{id}/rejections.csv — download the rejected-rows report. */
  downloadRejections(runId: string): Promise<void> {
    return authedDownload(`/v1/runs/${runId}/rejections.csv`, `rejections_${runId}.csv`);
  },
};
