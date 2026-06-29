/**
 * Run history types.
 *
 * History is sourced from the BACKEND (the durable DB run store) via
 * `GET /v1/runs` — see `hooks/useRun`. This module now only defines the shared
 * shape used by the history picker; the previous localStorage snapshot store has
 * been removed in favour of the database as the single source of truth.
 */
import type { RunStatus } from '@/lib/api';

export interface RunHistoryEntry {
  runId: string;
  tenantId: string;
  status: RunStatus;
  createdAt: string;
  /** Original upload filename, when known (not persisted by the backend list). */
  fileName?: string;
  rowsAccepted: number;
  rowsQuarantined: number;
}
