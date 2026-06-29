/**
 * Content registry: slug → typed Block[] page. Each page is its own TS module
 * (no Markdown files). Keep this in sync with ../manifest.ts.
 */
import type { Block } from '../blocks';
import overview from './overview';
import quickstart from './quickstart';
import architecture from './architecture';
import exceptionTypes from './exception-types';
import resolutionPaths from './resolution-paths';
import severityPriority from './severity-priority';
import fileImport from './file-import';
import sampleData from './sample-data';
import dashboards from './dashboards';
import roleGuides from './role-guides';
import adminGuide from './admin-guide';
import apiReference from './api-reference';
import security from './security';
import compliance from './compliance';
import troubleshooting from './troubleshooting';
import faq from './faq';
import releaseNotes from './release-notes';

export const DOC_CONTENT: Record<string, Block[]> = {
  overview,
  quickstart,
  architecture,
  'exception-types': exceptionTypes,
  'resolution-paths': resolutionPaths,
  'severity-priority': severityPriority,
  'file-import': fileImport,
  'sample-data': sampleData,
  dashboards,
  'role-guides': roleGuides,
  'admin-guide': adminGuide,
  'api-reference': apiReference,
  security,
  compliance,
  troubleshooting,
  faq,
  'release-notes': releaseNotes,
};
