/**
 * SLA timing for the "at risk" cockpit.
 *
 * The backend treats an item as at risk when it has already been outstanding
 * longer than its SLA allows: `days_outstanding * 24 >= sla_hours`
 * (app/scoring/priority.py). We mirror that exactly, but express it as a live
 * deadline so the UI can show a countdown that ticks in real time.
 *
 * Model: approximate when the invoice was received as `run_start − age`, then
 * `deadline = received + sla_hours`. At run-start this reduces to the backend's
 * rule (remaining ≤ 0 ⟺ days_outstanding*24 ≥ sla_hours); as wall-clock time
 * advances, the remaining time counts down.
 */

/** Mirrors the backend `comms_sla_due_soon_hours` (app/config.py). */
export const SLA_DUE_SOON_HOURS = 4;

const MS_PER_HOUR = 3_600_000;
const MS_PER_DAY = 86_400_000;

export type SlaStatus = 'breached' | 'due_soon' | 'on_track' | 'unknown';

export interface SlaInfo {
  status: SlaStatus;
  /** Absolute deadline (ms epoch), or null when SLA can't be computed. */
  deadlineMs: number | null;
  /** Time left in ms; negative means overdue. Null when unknown. */
  remainingMs: number | null;
}

export function computeSla(
  runCreatedAt: string,
  daysOutstanding: number,
  slaHours: number | undefined,
  nowMs: number,
  slaDays?: number | null,
): SlaInfo {
  // The SLA window comes from the invoice's own sla_days (CSV) when present,
  // otherwise the routing rule's sla_hours. Mirrors the backend (comms/sla.py).
  if (slaDays == null && slaHours == null) {
    return { status: 'unknown', deadlineMs: null, remainingMs: null };
  }
  const createdMs = new Date(runCreatedAt).getTime();
  if (Number.isNaN(createdMs)) return { status: 'unknown', deadlineMs: null, remainingMs: null };

  const receivedMs = createdMs - (daysOutstanding || 0) * MS_PER_DAY;
  const windowMs = slaDays != null ? slaDays * MS_PER_DAY : (slaHours as number) * MS_PER_HOUR;
  const deadlineMs = receivedMs + windowMs;
  const remainingMs = deadlineMs - nowMs;

  const status: SlaStatus =
    remainingMs <= 0 ? 'breached' : remainingMs <= SLA_DUE_SOON_HOURS * MS_PER_HOUR ? 'due_soon' : 'on_track';
  return { status, deadlineMs, remainingMs };
}

/** Human countdown like "2d 3h", "5h 12m", "42m 18s", or "overdue 3h 5m". */
export function formatRemaining(remainingMs: number): string {
  const overdue = remainingMs < 0;
  let ms = Math.abs(remainingMs);
  const d = Math.floor(ms / MS_PER_DAY);
  ms -= d * MS_PER_DAY;
  const h = Math.floor(ms / MS_PER_HOUR);
  ms -= h * MS_PER_HOUR;
  const m = Math.floor(ms / 60_000);
  ms -= m * 60_000;
  const s = Math.floor(ms / 1000);

  let label: string;
  if (d > 0) label = `${d}d ${h}h`;
  else if (h > 0) label = `${h}h ${m}m`;
  else label = `${m}m ${s}s`;
  return overdue ? `overdue ${label}` : label;
}

/** Short absolute deadline label, e.g. "Jun 26, 14:30". */
export function formatDeadline(deadlineMs: number): string {
  return new Date(deadlineMs).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}
