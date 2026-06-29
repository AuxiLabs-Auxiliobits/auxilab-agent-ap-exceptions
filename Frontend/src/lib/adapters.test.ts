import { describe, it, expect } from 'vitest';
import {
  severityToBucket,
  buildBucketMap,
  toExceptions,
  toDashboardStats,
  toCommunications,
  toAnalyticsData,
} from './adapters';
import type {
  ClassificationResult,
  CommunicationDraft,
  DashboardMetrics,
  ExceptionRow,
  PriorityQueues,
  ResolutionDecision,
  ResultItem,
} from './api';

const CREATED_AT = '2026-01-01T00:00:00Z';

function row(over: Partial<ExceptionRow> = {}): ExceptionRow {
  return {
    invoice_id: 'INV-1',
    vendor_name: 'Oracle',
    invoice_amount: '1000',
    po_number: 'PO-1',
    exception_type: 'Price Variance',
    exception_description: 'desc',
    days_outstanding: 5,
    approver_assigned: 'jane',
    ...over,
  };
}

function classification(over: Partial<ClassificationResult> = {}): ClassificationResult {
  return {
    invoice_id: 'INV-1',
    primary_exception_type: 'Price Variance',
    root_cause: 'root cause',
    severity_ai_suggested: 'HIGH',
    severity: 'HIGH',
    confidence_score: 0.834,
    rationale: 'because',
    model_id: 'm',
    prompt_version: 'v1',
    ...over,
  };
}

function resolution(over: Partial<ResolutionDecision> = {}): ResolutionDecision {
  return {
    invoice_id: 'INV-1',
    resolution_path: 'ESCALATE_CONTROLLER',
    rule_id: 'r1',
    rule_version: 'v1',
    rule_trace: [],
    requires_communication: true,
    sla_hours: 8,
    ...over,
  };
}

function draft(over: Partial<CommunicationDraft> = {}): CommunicationDraft {
  return {
    invoice_id: 'INV-1',
    channel: 'finance_note',
    recipient_hint: 'Finance Controller',
    subject: 'Subject',
    body: 'Body',
    tone: 'professional',
    template_id: 't',
    model_id: 'm',
    is_edited_by_human: false,
    send_status: 'draft',
    ...over,
  };
}

function item(over: Partial<ResultItem> = {}): ResultItem {
  return {
    invoice_id: 'INV-1',
    row: row(),
    classification: classification(),
    resolution: resolution(),
    draft: draft(),
    ...over,
  };
}

describe('severityToBucket', () => {
  it('maps UI severities to priority buckets', () => {
    expect(severityToBucket('High')).toBe('HIGH');
    expect(severityToBucket('Medium')).toBe('MEDIUM');
    expect(severityToBucket('Low')).toBe('LOW');
  });
});

describe('buildBucketMap', () => {
  it('flattens priority queues into an invoice->bucket map', () => {
    const queues: PriorityQueues = {
      high: [{ invoice_id: 'A', priority_score: 0.9, bucket: 'HIGH', drivers: [] }],
      medium: [{ invoice_id: 'B', priority_score: 0.5, bucket: 'MEDIUM', drivers: [] }],
      low: [{ invoice_id: 'C', priority_score: 0.1, bucket: 'LOW', drivers: [] }],
    };
    const map = buildBucketMap(queues);
    expect(map.get('A')).toBe('HIGH');
    expect(map.get('B')).toBe('MEDIUM');
    expect(map.get('C')).toBe('LOW');
    expect(buildBucketMap(null).size).toBe(0);
  });
});

describe('toExceptions', () => {
  it('maps backend fields/enums into the UI Exception shape', () => {
    const [exc] = toExceptions([item()], CREATED_AT, null);
    expect(exc.invoiceId).toBe('INV-1');
    expect(exc.vendorName).toBe('Oracle');
    expect(exc.invoiceAmount).toBe(1000); // string -> number
    expect(exc.severity).toBe('High'); // HIGH -> High
    expect(exc.confidence).toBe(83); // 0.834 -> 83
    expect(exc.status).toBe('Escalated'); // ESCALATE_CONTROLLER
    expect(exc.exceptionType).toBe('Price Variance');
  });

  it('renames "Duplicate" to "Duplicate Invoice"', () => {
    const [exc] = toExceptions(
      [item({ classification: classification({ primary_exception_type: 'Duplicate' }) })],
      CREATED_AT,
      null,
    );
    expect(exc.exceptionType).toBe('Duplicate Invoice');
  });

  it('prefers the priority-queue bucket over the severity-derived one', () => {
    const queues: PriorityQueues = {
      high: [],
      medium: [{ invoice_id: 'INV-1', priority_score: 0.5, bucket: 'MEDIUM', drivers: [] }],
      low: [],
    };
    const [exc] = toExceptions([item()], CREATED_AT, queues);
    // severity is HIGH (would be HIGH bucket) but the queue says MEDIUM
    expect(exc.priority).toBe('MEDIUM');
  });

  it('falls back to Pending status when unclassified', () => {
    const [exc] = toExceptions(
      [item({ classification: null, resolution: null })],
      CREATED_AT,
      null,
    );
    expect(exc.status).toBe('Pending');
  });

  it('reflects a closed case as Resolved/cleared so every status-driven view updates', () => {
    const cases = {
      'INV-1': { invoice_id: 'INV-1', status: 'RESOLVED' as const },
    };
    const [exc] = toExceptions([item()], CREATED_AT, null, cases);
    expect(exc.caseStatus).toBe('RESOLVED');
    expect(exc.status).toBe('Resolved'); // was 'Escalated' — now cleared on dashboard/queue
  });

  it('defaults caseStatus to OPEN when no case has been opened', () => {
    const [exc] = toExceptions([item()], CREATED_AT, null);
    expect(exc.caseStatus).toBe('OPEN');
    expect(exc.status).toBe('Escalated'); // unaffected
  });
});

describe('toCommunications', () => {
  it('maps channels and skips items without a draft', () => {
    const comms = toCommunications(
      [
        item({ invoice_id: 'INV-1', draft: draft({ channel: 'vendor_email' }) }),
        item({ invoice_id: 'INV-2', draft: null }),
        item({ invoice_id: 'INV-3', draft: draft({ channel: 'slack' }) }),
      ],
      CREATED_AT,
    );
    expect(comms).toHaveLength(2);
    expect(comms[0].type).toBe('Vendor Email');
    expect(comms[1].type).toBe('Internal Slack');
  });
});

describe('toDashboardStats', () => {
  const metrics: DashboardMetrics = {
    total_exceptions: 25,
    auto_resolvable_count: 5,
    escalations_required: 8,
    total_exception_value: '442450',
    breakdown_by_type: { 'Price Variance': 8 },
    breakdown_by_severity: { HIGH: 8, MEDIUM: 13, LOW: 4 },
    breakdown_by_resolution_path: { ESCALATE_CONTROLLER: 4 },
    top_5_actionable: [],
    sla_at_risk_count: 25,
    average_confidence: 0.83,
  };

  it('derives counts, value and resolution rate', () => {
    const stats = toDashboardStats(metrics);
    expect(stats.totalExceptions).toBe(25);
    expect(stats.highSeverityCount).toBe(8);
    expect(stats.totalExceptionValue).toBe(442450);
    expect(stats.resolutionRate).toBe(20); // 5/25 = 20%
  });

  it('produces analytics series including value-by-type', () => {
    const data = toAnalyticsData(metrics, [item({ row: row({ invoice_amount: '1000' }) })]);
    expect(data.exceptionsByType[0]).toEqual({ name: 'Price Variance', value: 8 });
    expect(data.valueByType[0]).toEqual({ name: 'Price Variance', value: 1000 });
    expect(data.topVendors[0]).toEqual({ name: 'Oracle', exceptions: 1 });
  });
});
