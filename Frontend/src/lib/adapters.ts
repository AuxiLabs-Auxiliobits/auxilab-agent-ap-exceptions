/**
 * Maps backend response shapes (`src/lib/api.ts`) into the UI domain types
 * (`@/types`). The UI components stay unchanged — every backend/UI field-name
 * and enum mismatch is reconciled here in one place.
 */
import type {
  BackendExceptionType,
  BackendSeverity,
  Case,
  CaseStatus,
  ClassificationResult,
  CommunicationDraft,
  DashboardMetrics,
  PriorityQueues,
  ResolutionPathEnum,
  ResultItem,
} from '@/lib/api';
import type {
  ActivityLog,
  AnalyticsData,
  Communication,
  DashboardStats,
  Exception,
  ExceptionStatus,
  ExceptionType,
  Priority,
  Severity,
} from '@/types';
import { resolutionPathLabel } from '@/lib/resolutionLabels';

// ---- enum / label mapping ------------------------------------------------

const SEVERITY_MAP: Record<BackendSeverity, Severity> = {
  HIGH: 'High',
  MEDIUM: 'Medium',
  LOW: 'Low',
};

const EXCEPTION_TYPE_MAP: Record<BackendExceptionType, ExceptionType> = {
  'Price Variance': 'Price Variance',
  'Quantity Mismatch': 'Quantity Mismatch',
  'Missing PO': 'Missing PO',
  Duplicate: 'Duplicate Invoice',
  'Unapproved Vendor': 'Unapproved Vendor',
  'GRN Not Received': 'GRN Not Received',
  Other: 'Price Variance',
};

/** Map a backend resolution path to a coarse UI status for the queue table. */
const RESOLUTION_STATUS_MAP: Record<ResolutionPathEnum, ExceptionStatus> = {
  AUTO_APPROVE: 'Auto-Resolved',
  REQUEST_PO: 'In Progress',
  REQUEST_GRN: 'In Progress',
  VENDOR_VALIDATION_REVIEW: 'In Progress',
  ESCALATE_CONTROLLER: 'Escalated',
  HOLD_INVESTIGATION: 'Escalated',
  MANUAL_REVIEW: 'Pending',
};

export function severityToBucket(sev: Severity): Priority {
  return sev === 'High' ? 'HIGH' : sev === 'Medium' ? 'MEDIUM' : 'LOW';
}

function normalizeExceptionType(
  classification: ClassificationResult | null,
  rawType: string,
): ExceptionType {
  if (classification) {
    return EXCEPTION_TYPE_MAP[classification.primary_exception_type] ?? 'Price Variance';
  }
  // Fall back to the ERP-declared type string when not yet classified.
  if ((Object.values(EXCEPTION_TYPE_MAP) as string[]).includes(rawType)) {
    return rawType as ExceptionType;
  }
  if (rawType in EXCEPTION_TYPE_MAP) {
    return EXCEPTION_TYPE_MAP[rawType as BackendExceptionType];
  }
  return 'Price Variance';
}

// ---- result item -> Exception -------------------------------------------

const CLOSED_CASE_STATUSES = new Set<CaseStatus>(['RESOLVED', 'WONT_FIX']);

export function toException(
  item: ResultItem,
  createdAt: string,
  bucketByInvoice: Map<string, Priority>,
  caseStatus?: CaseStatus,
): Exception {
  const { row, classification, resolution } = item;
  const severity: Severity = classification
    ? SEVERITY_MAP[classification.severity]
    : 'Medium';

  // A closed case (resolved / won't-fix) is "cleared": reflect it in the coarse
  // status so every status-driven view (dashboard reconciliation strip, queue
  // table) shows it as resolved without each one needing case-specific logic.
  const status: ExceptionStatus =
    caseStatus && CLOSED_CASE_STATUSES.has(caseStatus)
      ? 'Resolved'
      : resolution
        ? RESOLUTION_STATUS_MAP[resolution.resolution_path] ?? 'Pending'
        : classification
          ? 'In Progress'
          : 'Pending';

  return {
    id: item.invoice_id,
    invoiceId: row.invoice_id,
    vendorName: row.vendor_name,
    invoiceAmount: Number(row.invoice_amount),
    exceptionType: normalizeExceptionType(classification, row.exception_type),
    severity,
    daysOutstanding: row.days_outstanding,
    assignedApprover: row.approver_assigned ?? '—',
    status,
    createdAt,
    priority: bucketByInvoice.get(item.invoice_id) ?? severityToBucket(severity),
    rootCause: classification?.root_cause,
    confidence: classification
      ? Math.round(classification.confidence_score * 100)
      : undefined,
    reasoning: classification?.rationale,
    slaHours: resolution?.sla_hours,
    slaDays: row.sla_days ?? undefined,
    resolutionPath: resolution?.resolution_path,
    caseStatus: caseStatus ?? 'OPEN',
  };
}

/** invoice_id -> priority bucket, derived from the priority queues payload. */
export function buildBucketMap(queues: PriorityQueues | null): Map<string, Priority> {
  const map = new Map<string, Priority>();
  if (!queues) return map;
  for (const e of queues.high) map.set(e.invoice_id, 'HIGH');
  for (const e of queues.medium) map.set(e.invoice_id, 'MEDIUM');
  for (const e of queues.low) map.set(e.invoice_id, 'LOW');
  return map;
}

export function toExceptions(
  results: ResultItem[],
  createdAt: string,
  queues: PriorityQueues | null,
  cases?: Record<string, Case>,
): Exception[] {
  const buckets = buildBucketMap(queues);
  return results.map((r) =>
    toException(r, createdAt, buckets, cases?.[r.invoice_id]?.status),
  );
}

// ---- draft -> Communication ---------------------------------------------

function channelToCommType(channel: CommunicationDraft['channel']): Communication['type'] {
  switch (channel) {
    case 'vendor_email':
      return 'Vendor Email';
    case 'slack':
      return 'Internal Slack';
    case 'finance_note':
    case 'internal_email':
    default:
      return 'Escalation Note';
  }
}

export function toCommunication(
  draft: CommunicationDraft,
  createdAt: string,
): Communication {
  return {
    id: `${draft.invoice_id}-${draft.channel}`,
    type: channelToCommType(draft.channel),
    subject: draft.subject ?? `Invoice ${draft.invoice_id}`,
    content: draft.body,
    recipient: draft.recipient ?? draft.recipient_hint,
    createdAt: draft.sent_at ?? createdAt,
    invoiceId: draft.invoice_id,
    channel: draft.channel,
    sendStatus: draft.send_status,
    sendProvider: draft.send_provider,
    sentAt: draft.sent_at,
    isEdited: draft.is_edited_by_human,
  };
}

export function toCommunications(
  results: ResultItem[],
  createdAt: string,
): Communication[] {
  return results
    .filter((r): r is ResultItem & { draft: CommunicationDraft } => r.draft != null)
    .map((r) => toCommunication(r.draft, createdAt));
}

// ---- metrics -> DashboardStats ------------------------------------------

export function toDashboardStats(metrics: DashboardMetrics): DashboardStats {
  const total = metrics.total_exceptions || 0;
  return {
    totalExceptions: total,
    autoResolvable: metrics.auto_resolvable_count,
    escalationsRequired: metrics.escalations_required,
    totalExceptionValue: Number(metrics.total_exception_value),
    highSeverityCount: metrics.breakdown_by_severity?.HIGH ?? 0,
    resolutionRate: total
      ? Math.round((metrics.auto_resolvable_count / total) * 1000) / 10
      : 0,
    avgProcessingTime: Math.round(metrics.average_confidence * 100) / 100,
  };
}

// ---- metrics + results -> AnalyticsData ---------------------------------

function recordToSeries(
  record: Record<string, number>,
  relabel?: (k: string) => string,
): { name: string; value: number }[] {
  return Object.entries(record)
    .map(([name, value]) => ({ name: relabel ? relabel(name) : name, value }))
    .sort((a, b) => b.value - a.value);
}

export function toAnalyticsData(
  metrics: DashboardMetrics,
  results: ResultItem[],
): AnalyticsData {
  // Top vendors by exception count, derived from the run results.
  const vendorCounts = new Map<string, number>();
  // Dollar exposure per (classified) exception type.
  const valueByTypeMap = new Map<string, number>();
  for (const r of results) {
    const v = r.row.vendor_name;
    vendorCounts.set(v, (vendorCounts.get(v) ?? 0) + 1);

    const type = r.classification
      ? r.classification.primary_exception_type
      : r.row.exception_type;
    valueByTypeMap.set(
      type,
      (valueByTypeMap.get(type) ?? 0) + Number(r.row.invoice_amount),
    );
  }
  const topVendors = [...vendorCounts.entries()]
    .map(([name, exceptions]) => ({ name, exceptions }))
    .sort((a, b) => b.exceptions - a.exceptions)
    .slice(0, 5);

  const valueByType = [...valueByTypeMap.entries()]
    .map(([name, value]) => ({ name, value: Math.round(value) }))
    .sort((a, b) => b.value - a.value);

  return {
    exceptionsByType: recordToSeries(metrics.breakdown_by_type),
    severityDistribution: recordToSeries(metrics.breakdown_by_severity, (k) =>
      k === 'HIGH' ? 'High' : k === 'MEDIUM' ? 'Medium' : k === 'LOW' ? 'Low' : k,
    ),
    resolutionStatus: recordToSeries(
      metrics.breakdown_by_resolution_path,
      (k) => resolutionPathLabel(k),
    ),
    valueByType,
    topVendors,
  };
}

// ---- audit events -> ActivityLog ----------------------------------------

const ACTIVITY_LABELS: Record<string, string> = {
  NODE_START: 'Node Started',
  NODE_END: 'Node Completed',
  AI_CALL: 'AI Analysis',
  RULE_FIRE: 'Rule Applied',
  HUMAN_EDIT: 'Human Edit',
  APPROVAL: 'Approved',
  ERROR: 'Error',
  INGEST_QUARANTINE: 'Row Quarantined',
};

export function toActivityLog(
  events: { event_id: string; event_type: string; node_name: string; timestamp: string; invoice_id?: string | null; actor: string }[],
): ActivityLog[] {
  // Show the most recent activity first, capped to keep the timeline readable.
  return [...events]
    .reverse()
    .slice(0, 15)
    .map((e) => ({
      id: e.event_id,
      action: ACTIVITY_LABELS[e.event_type] ?? e.event_type,
      description: e.invoice_id
        ? `${e.node_name} · invoice ${e.invoice_id}`
        : e.node_name,
      timestamp: e.timestamp,
      status:
        e.event_type === 'ERROR'
          ? 'pending'
          : e.event_type === 'NODE_START'
            ? 'in-progress'
            : 'completed',
      user: e.actor,
    }));
}
