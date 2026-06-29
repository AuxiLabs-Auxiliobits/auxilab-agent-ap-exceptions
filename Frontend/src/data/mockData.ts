import type { Exception, ResolutionPath, Communication, ActivityLog, DashboardStats, AnalyticsData } from '@/types';

const vendors = [
  'SAP Enterprise Solutions',
  'Oracle Financial Services',
  'Microsoft Corporation',
  'Salesforce Inc.',
  'Adobe Systems',
  'Amazon Web Services',
  'Deloitte Consulting',
  'Accenture LLP',
  'IBM Global Services',
  'Cisco Systems',
];

const approvers = [
  'Sarah Johnson',
  'Michael Chen',
  'Emily Williams',
  'David Park',
  'Amanda Foster',
  'Robert Kim',
  'Jennifer Lee',
  'Christopher Martinez',
];

const exceptionTypes: Array<'Price Variance' | 'Missing PO' | 'Quantity Mismatch' | 'Duplicate Invoice' | 'Unapproved Vendor' | 'GRN Not Received' | 'Tax Discrepancy' | 'Payment Terms Mismatch'> = [
  'Price Variance',
  'Missing PO',
  'Quantity Mismatch',
  'Duplicate Invoice',
  'Unapproved Vendor',
  'GRN Not Received',
  'Tax Discrepancy',
  'Payment Terms Mismatch',
];

const statuses: Array<'Pending' | 'In Progress' | 'Auto-Resolved' | 'Escalated' | 'Resolved'> = [
  'Pending',
  'In Progress',
  'Auto-Resolved',
  'Escalated',
  'Resolved',
];

const severities: Array<'High' | 'Medium' | 'Low'> = ['High', 'Medium', 'Low'];

function generateRandomId(): string {
  return `INV-${Math.random().toString(36).substr(2, 9).toUpperCase()}`;
}

function generateRandomAmount(): number {
  return Math.floor(Math.random() * 45000) + 500;
}

function generateRandomDaysOutstanding(): number {
  return Math.floor(Math.random() * 45) + 1;
}

export const mockExceptions: Exception[] = Array.from({ length: 100 }, (_, i) => {
  const severity = severities[Math.floor(Math.random() * severities.length)];
  const status = statuses[Math.floor(Math.random() * statuses.length)];

  return {
    id: `EXC-${String(i + 1).padStart(4, '0')}`,
    invoiceId: generateRandomId(),
    vendorName: vendors[Math.floor(Math.random() * vendors.length)],
    invoiceAmount: generateRandomAmount(),
    exceptionType: exceptionTypes[Math.floor(Math.random() * exceptionTypes.length)],
    severity,
    daysOutstanding: generateRandomDaysOutstanding(),
    assignedApprover: approvers[Math.floor(Math.random() * approvers.length)],
    status,
    createdAt: new Date(Date.now() - Math.random() * 30 * 24 * 60 * 60 * 1000).toISOString(),
    priority: severity === 'High' ? 'HIGH' : severity === 'Medium' ? 'MEDIUM' : 'LOW',
    rootCause: 'Automated analysis determined discrepancy in vendor billing cycle',
    confidence: Math.floor(Math.random() * 20) + 80,
    reasoning: 'AI detected variance patterns consistent with historical vendor data. Similar exceptions resolved successfully in 94% of cases.',
  };
});

export const mockResolutionPaths: ResolutionPath[] = [
  {
    id: 'RES-001',
    type: 'Auto Approve',
    logic: 'Confidence > 95% and Amount < $5000',
    assignedTeam: 'AI Processing Engine',
    slaTime: '< 5 minutes',
    automationStatus: 'Automated',
    description: 'Automatically approves low-value exceptions with high AI confidence score',
  },
  {
    id: 'RES-002',
    type: 'Escalate to Finance Controller',
    logic: 'Severity = High or Amount > $20000',
    assignedTeam: 'Finance Controller Team',
    slaTime: '< 2 hours',
    automationStatus: 'Semi-Automated',
    description: 'Escalates critical exceptions to senior finance leadership for review',
  },
  {
    id: 'RES-003',
    type: 'Request Missing PO',
    logic: 'Exception Type = Missing PO',
    assignedTeam: 'Procurement Operations',
    slaTime: '< 24 hours',
    automationStatus: 'Semi-Automated',
    description: 'Initiates automated PO request workflow with procurement team',
  },
  {
    id: 'RES-004',
    type: 'Hold for Investigation',
    logic: 'Duplicate Invoice or Unapproved Vendor',
    assignedTeam: 'AP Audit Team',
    slaTime: '< 48 hours',
    automationStatus: 'Manual',
    description: 'Flags for detailed manual investigation by audit specialists',
  },
  {
    id: 'RES-005',
    type: 'Vendor Clarification Required',
    logic: 'Price Variance > 10% or Quantity Mismatch',
    assignedTeam: 'Vendor Relations',
    slaTime: '< 72 hours',
    automationStatus: 'Semi-Automated',
    description: 'Generates automated vendor communication requesting clarification',
  },
];

export const mockCommunications: Communication[] = [
  {
    id: 'COM-001',
    type: 'Vendor Email',
    subject: 'Invoice Discrepancy Notification - INV-2024-7832',
    content: `Dear Vendor Relations Team,

We have identified a price variance on Invoice INV-2024-7832 dated May 15, 2024.

Invoice Amount: $12,450.00
Expected Amount: $11,200.00
Variance: $1,250.00 (11.2%)

Please review and confirm the correct billing amount at your earliest convenience.

Best regards,
AP Exception Handling Agent`,
    recipient: 'vendor@sap-enterprise.com',
    createdAt: new Date().toISOString(),
  },
  {
    id: 'COM-002',
    type: 'Internal Slack',
    subject: 'High Severity Exception Alert',
    content: `:warning: **Exception Alert**

**Invoice ID:** INV-2024-9843
**Vendor:** Oracle Financial Services
**Amount:** $34,500.00
**Issue:** Unapproved Vendor

**Action Required:** Immediate finance controller review needed. This invoice exceeds the $20,000 threshold and requires expedited approval.

**Assigned to:** @sarah.johnson
**SLA:** 2 hours remaining`,
    recipient: '#finance-exceptions',
    createdAt: new Date().toISOString(),
  },
  {
    id: 'COM-003',
    type: 'Escalation Note',
    subject: 'Critical Exception Escalation - Executive Review Required',
    content: `**ESCALATION NOTICE**

**Severity:** Critical
**Exception ID:** EXC-0047
**Vendor:** Microsoft Corporation
**Invoice Amount:** $45,000.00

**Issue Summary:**
Duplicate invoice detected for services already processed in Q1. This requires immediate attention due to the high financial impact and compliance implications.

**Recommended Action:**
1. Contact Microsoft billing department urgently
2. Halt payment processing
3. Conduct forensic audit of related transactions

**Escalated by:** AI Exception Agent
**Escalated to:** CFO Office`,
    recipient: 'executive-finance@company.com',
    createdAt: new Date().toISOString(),
  },
];

export const mockActivityLog: ActivityLog[] = [
  {
    id: 'ACT-001',
    action: 'Queue Uploaded',
    description: 'Invoice batch uploaded from SAP integration',
    timestamp: new Date(Date.now() - 3600000).toISOString(),
    status: 'completed',
    user: 'System Integration',
  },
  {
    id: 'ACT-002',
    action: 'Classification Completed',
    description: 'AI analysis completed for 47 exceptions',
    timestamp: new Date(Date.now() - 2700000).toISOString(),
    status: 'completed',
    user: 'AI Processing Engine',
  },
  {
    id: 'ACT-003',
    action: 'Resolution Assigned',
    description: 'Auto-approval triggered for 23 exceptions',
    timestamp: new Date(Date.now() - 1800000).toISOString(),
    status: 'completed',
    user: 'Workflow Manager',
  },
  {
    id: 'ACT-004',
    action: 'Communication Drafted',
    description: 'Vendor emails generated for clarification requests',
    timestamp: new Date(Date.now() - 900000).toISOString(),
    status: 'completed',
    user: 'Communication Agent',
  },
  {
    id: 'ACT-005',
    action: 'Review Pending',
    description: '12 exceptions awaiting manual review',
    timestamp: new Date().toISOString(),
    status: 'in-progress',
    user: 'Finance Controller',
  },
];

export const mockDashboardStats: DashboardStats = {
  totalExceptions: 847,
  autoResolvable: 412,
  escalationsRequired: 89,
  totalExceptionValue: 2450000,
  highSeverityCount: 127,
  resolutionRate: 78.4,
  avgProcessingTime: 4.2,
};

export const mockAnalyticsData: AnalyticsData = {
  exceptionsByType: [
    { name: 'Price Variance', value: 234 },
    { name: 'Missing PO', value: 189 },
    { name: 'Quantity Mismatch', value: 156 },
    { name: 'Duplicate Invoice', value: 98 },
    { name: 'Unapproved Vendor', value: 87 },
    { name: 'GRN Not Received', value: 65 },
    { name: 'Tax Discrepancy', value: 12 },
    { name: 'Payment Terms Mismatch', value: 6 },
  ],
  severityDistribution: [
    { name: 'High', value: 127 },
    { name: 'Medium', value: 398 },
    { name: 'Low', value: 322 },
  ],
  resolutionStatus: [
    { name: 'Auto-Resolved', value: 312 },
    { name: 'Manually Resolved', value: 234 },
    { name: 'In Progress', value: 156 },
    { name: 'Pending', value: 145 },
  ],
  valueByType: [
    { name: 'Price Variance', value: 234000 },
    { name: 'Missing PO', value: 189000 },
    { name: 'Quantity Mismatch', value: 156000 },
    { name: 'Duplicate Invoice', value: 98000 },
    { name: 'Unapproved Vendor', value: 87000 },
  ],
  topVendors: [
    { name: 'SAP Enterprise', exceptions: 89 },
    { name: 'Oracle Financial', exceptions: 76 },
    { name: 'Microsoft Corp', exceptions: 68 },
    { name: 'Salesforce Inc', exceptions: 54 },
    { name: 'Adobe Systems', exceptions: 45 },
  ],
};
