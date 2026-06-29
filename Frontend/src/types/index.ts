export interface Exception {
  id: string;
  invoiceId: string;
  vendorName: string;
  invoiceAmount: number;
  exceptionType: ExceptionType;
  severity: Severity;
  daysOutstanding: number;
  assignedApprover: string;
  status: ExceptionStatus;
  createdAt: string;
  priority: Priority;
  rootCause?: string;
  confidence?: number;
  reasoning?: string;
  /** Resolution SLA window in hours (from the routing decision), if resolved. */
  slaHours?: number;
  /** Per-invoice SLA window in days from the CSV (overrides slaHours when set). */
  slaDays?: number;
  /** Backend resolution-path enum value (e.g. "ESCALATE_CONTROLLER"), if resolved. */
  resolutionPath?: string;
  /**
   * Human resolution-lifecycle status from the Resolution Tracker, if a case has
   * been opened for this invoice. Drives status-aware views: a closed case
   * (RESOLVED / WONT_FIX) is "cleared" — off the SLA clock and counted resolved
   * on the dashboard. Defaults to OPEN when no case has been touched yet.
   */
  caseStatus?: 'OPEN' | 'IN_PROGRESS' | 'RESOLVED' | 'WONT_FIX';
}

export type ExceptionType =
  | 'Price Variance'
  | 'Missing PO'
  | 'Quantity Mismatch'
  | 'Duplicate Invoice'
  | 'Unapproved Vendor'
  | 'GRN Not Received'
  | 'Tax Discrepancy'
  | 'Payment Terms Mismatch';

export type Severity = 'High' | 'Medium' | 'Low';

export type ExceptionStatus =
  | 'Pending'
  | 'In Progress'
  | 'Auto-Resolved'
  | 'Escalated'
  | 'Resolved';

export type Priority = 'HIGH' | 'MEDIUM' | 'LOW';

export interface ResolutionPath {
  id: string;
  type: ResolutionType;
  logic: string;
  assignedTeam: string;
  slaTime: string;
  automationStatus: 'Automated' | 'Semi-Automated' | 'Manual';
  description: string;
}

export type ResolutionType =
  | 'Auto Approve'
  | 'Escalate to Finance Controller'
  | 'Request Missing PO'
  | 'Hold for Investigation'
  | 'Vendor Clarification Required';

export type CommSendStatus = 'draft' | 'dryrun' | 'sent' | 'failed' | 'skipped';

export interface Communication {
  id: string;
  type: 'Vendor Email' | 'Internal Slack' | 'Escalation Note';
  subject: string;
  content: string;
  recipient: string;
  createdAt: string;
  // Backend linkage (present when sourced from a live run; optional so the
  // legacy mock shape still satisfies this interface).
  invoiceId?: string;
  channel?: string;
  sendStatus?: CommSendStatus;
  sendProvider?: string | null;
  sentAt?: string | null;
  isEdited?: boolean;
}

export interface ActivityLog {
  id: string;
  action: string;
  description: string;
  timestamp: string;
  status: 'completed' | 'in-progress' | 'pending';
  user?: string;
}

export interface DashboardStats {
  totalExceptions: number;
  autoResolvable: number;
  escalationsRequired: number;
  totalExceptionValue: number;
  highSeverityCount: number;
  resolutionRate: number;
  avgProcessingTime: number;
}

export interface AnalyticsData {
  exceptionsByType: { name: string; value: number }[];
  severityDistribution: { name: string; value: number }[];
  resolutionStatus: { name: string; value: number }[];
  // Dollar exposure per exception type — meaningful for a single run (replaces
  // the multi-run "monthly trend", which the single-run backend can't fill).
  valueByType: { name: string; value: number }[];
  topVendors: { name: string; exceptions: number }[];
}
