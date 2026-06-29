/**
 * Documentation site map.
 *
 * Each entry maps a URL slug (/docs/:slug) to a typed content module
 * (./content/<slug>.ts) and presentation metadata. The order here is the order
 * rendered in the sidebar and used for prev/next navigation.
 */
import {
  Home,
  Rocket,
  Workflow,
  Tags,
  GitBranch,
  SlidersHorizontal,
  Upload,
  FileSpreadsheet,
  LayoutDashboard,
  Users,
  Wrench,
  Code2,
  ShieldCheck,
  ClipboardCheck,
  LifeBuoy,
  HelpCircle,
  FileText,
  Boxes,
  type LucideIcon,
} from 'lucide-react';

export interface DocPageMeta {
  slug: string;
  title: string;
  /** One-line summary shown on the docs home cards and in search results. */
  summary: string;
  icon: LucideIcon;
}

export interface DocGroup {
  title: string;
  /** Short label for the docs home section grid. */
  blurb: string;
  icon: LucideIcon;
  pages: DocPageMeta[];
}

export const DOC_GROUPS: DocGroup[] = [
  {
    title: 'Getting Started',
    blurb: 'What the platform does and how to run your first reconciliation.',
    icon: Rocket,
    pages: [
      { slug: 'overview', title: 'Product Overview', summary: 'What the AP Exception Agent is, who it is for, and how it works end to end.', icon: Home },
      { slug: 'quickstart', title: 'Quickstart', summary: 'Your first upload, exception review, dashboard, and resolution — in five steps.', icon: Rocket },
      { slug: 'architecture', title: 'Architecture', summary: 'The pipeline, where AI is used, and where deterministic code guarantees the outcome.', icon: Workflow },
    ],
  },
  {
    title: 'Core Concepts',
    blurb: 'The exception taxonomy, routing rules, and how work is prioritized.',
    icon: Boxes,
    pages: [
      { slug: 'exception-types', title: 'Exception Types', summary: 'Every exception the agent detects — definition, detection logic, causes, and resolution.', icon: Tags },
      { slug: 'resolution-paths', title: 'Resolution Paths', summary: 'The deterministic rule engine: routing rules, SLAs, teams, and decision tree.', icon: GitBranch },
      { slug: 'severity-priority', title: 'Severity & Priority', summary: 'How severity is set and how the priority queue is scored and bucketed.', icon: SlidersHorizontal },
    ],
  },
  {
    title: 'Working with Data',
    blurb: 'File formats, validation, and ready-to-use samples.',
    icon: Upload,
    pages: [
      { slug: 'file-import', title: 'File Import (CSV & JSON)', summary: 'Required and optional columns, validation rules, aliases, size limits, and rejection reports.', icon: Upload },
      { slug: 'sample-data', title: 'Sample Data', summary: 'Copy-paste sample CSV, JSON, exception records, and dashboard outputs.', icon: FileSpreadsheet },
    ],
  },
  {
    title: 'Using the Console',
    blurb: 'Guides for every screen and every role.',
    icon: LayoutDashboard,
    pages: [
      { slug: 'dashboards', title: 'Dashboards', summary: 'Every dashboard explained: purpose, metrics, calculations, filters, and actions.', icon: LayoutDashboard },
      { slug: 'role-guides', title: 'Role Guides', summary: 'Day-in-the-life workflows for AP Clerk, AP Manager, Controller, Procurement, and Auditor.', icon: Users },
      { slug: 'admin-guide', title: 'Administrator Guide', summary: 'Configuration, roles, notifications, workflow, import, and retention settings.', icon: Wrench },
    ],
  },
  {
    title: 'Developers',
    blurb: 'Integrate with the REST API.',
    icon: Code2,
    pages: [
      { slug: 'api-reference', title: 'API Reference', summary: 'Authentication, every endpoint, request/response shapes, error codes, and rate limits.', icon: Code2 },
    ],
  },
  {
    title: 'Trust & Compliance',
    blurb: 'Security controls, audit trails, and finance controls.',
    icon: ShieldCheck,
    pages: [
      { slug: 'security', title: 'Security', summary: 'Authentication, tenant isolation, encryption, file-upload safety, and PII handling.', icon: ShieldCheck },
      { slug: 'compliance', title: 'Compliance & Audit', summary: 'Audit trails, SOX considerations, data retention, and finance/operational controls.', icon: ClipboardCheck },
    ],
  },
  {
    title: 'Help',
    blurb: 'Fix problems and learn what changed.',
    icon: LifeBuoy,
    pages: [
      { slug: 'troubleshooting', title: 'Troubleshooting', summary: 'Upload failures, missing columns, duplicate detection, notification and dashboard issues.', icon: LifeBuoy },
      { slug: 'faq', title: 'FAQ', summary: 'Fifty answers covering product, data, AI, security, billing, and operations.', icon: HelpCircle },
      { slug: 'release-notes', title: 'Release Notes', summary: 'Versioned changelog and the template we use for every release.', icon: FileText },
    ],
  },
];

/** Flat, ordered list of all pages — used for prev/next and lookups. */
export const ALL_DOC_PAGES: DocPageMeta[] = DOC_GROUPS.flatMap((g) => g.pages);

export function findDocIndex(slug: string): number {
  return ALL_DOC_PAGES.findIndex((p) => p.slug === slug);
}
