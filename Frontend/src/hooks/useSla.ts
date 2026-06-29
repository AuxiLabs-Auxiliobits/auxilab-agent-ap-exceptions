/**
 * Shared SLA summary for the current run. Computes, per actionable exception, a
 * live SLA status and sorts by time-to-breach — so the SLA cockpit, the sidebar
 * badge, and the header notifications all read from one source of truth.
 *
 * `tickMs` controls how often the countdown advances: the cockpit wants 1s for a
 * smooth timer; the sidebar/header are happy at 30s.
 */
import { useEffect, useMemo, useState } from 'react';
import { useRun } from '@/hooks/useRun';
import { computeSla, type SlaInfo } from '@/lib/sla';
import type { Exception } from '@/types';

export interface SlaRow {
  ex: Exception;
  sla: SlaInfo;
  /** True when the case is resolved/won't-fix — off the clock, excluded from counts. */
  closed: boolean;
}

export interface SlaSummary {
  /** Actionable rows (have an SLA, not auto-cleared), sorted most-urgent first.
   *  Includes closed rows (flagged) so the Resolution Tracker can still show
   *  them; SLA-risk counts below exclude them. */
  rows: SlaRow[];
  breached: number;
  dueSoon: number;
  onTrack: number;
  /** breached + dueSoon — the "needs attention now" total (closed excluded). */
  atRisk: number;
}

const CLOSED = new Set(['RESOLVED', 'WONT_FIX']);

export function useSla(tickMs = 30_000): SlaSummary {
  const { exceptions, createdAt } = useRun();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), tickMs);
    return () => clearInterval(t);
  }, [tickMs]);

  return useMemo(() => {
    const base = createdAt ?? new Date(0).toISOString();
    const rows: SlaRow[] = exceptions
      .filter(
        (ex) =>
          (ex.slaHours != null || ex.slaDays != null) &&
          ex.resolutionPath !== 'AUTO_APPROVE',
      )
      .map((ex) => ({
        ex,
        sla: computeSla(base, ex.daysOutstanding, ex.slaHours, now, ex.slaDays),
        closed: CLOSED.has(ex.caseStatus ?? 'OPEN'),
      }))
      .filter((r) => r.sla.status !== 'unknown')
      .sort((a, b) => (a.sla.remainingMs ?? 0) - (b.sla.remainingMs ?? 0));

    // Counts reflect only items still on the clock — a resolved/won't-fix case
    // is off the clock, so it stops counting as breached/due-soon/at-risk.
    let breached = 0;
    let dueSoon = 0;
    let onTrack = 0;
    for (const r of rows) {
      if (r.closed) continue;
      if (r.sla.status === 'breached') breached++;
      else if (r.sla.status === 'due_soon') dueSoon++;
      else if (r.sla.status === 'on_track') onTrack++;
    }
    return { rows, breached, dueSoon, onTrack, atRisk: breached + dueSoon };
  }, [exceptions, createdAt, now]);
}
