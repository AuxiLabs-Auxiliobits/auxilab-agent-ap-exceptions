import { describe, it, expect } from 'vitest';
import { computeSla, formatRemaining, SLA_DUE_SOON_HOURS } from './sla';

// Fixed run-start so the math is deterministic (no Date.now()).
const RUN_START = '2026-06-26T12:00:00Z';
const runStartMs = new Date(RUN_START).getTime();
const HOUR = 3_600_000;

describe('computeSla', () => {
  it('returns unknown when slaHours is missing', () => {
    expect(computeSla(RUN_START, 0, undefined, runStartMs).status).toBe('unknown');
  });

  it('mirrors the backend age-based rule at run-start (days*24 >= sla => breached)', () => {
    // 2 days old, 24h SLA → already overdue at run-start.
    const overdue = computeSla(RUN_START, 2, 24, runStartMs);
    expect(overdue.status).toBe('breached');
    expect(overdue.remainingMs).toBeLessThanOrEqual(0);

    // 0 days old, 48h SLA → comfortably on track.
    const fresh = computeSla(RUN_START, 0, 48, runStartMs);
    expect(fresh.status).toBe('on_track');
    expect(fresh.remainingMs).toBeGreaterThan(0);
  });

  it('flags due_soon within the 4h window', () => {
    // received = now - 23h, 24h SLA → 1h left → due soon.
    const dueSoon = computeSla(RUN_START, 23 / 24, 24, runStartMs);
    expect(dueSoon.status).toBe('due_soon');
    expect(dueSoon.remainingMs).toBeLessThanOrEqual(SLA_DUE_SOON_HOURS * HOUR);
    expect(dueSoon.remainingMs).toBeGreaterThan(0);
  });

  it('counts down as wall-clock advances', () => {
    const t0 = computeSla(RUN_START, 0, 10, runStartMs);
    const t1 = computeSla(RUN_START, 0, 10, runStartMs + HOUR);
    expect((t1.remainingMs ?? 0)).toBeLessThan(t0.remainingMs ?? 0);
    expect((t0.remainingMs ?? 0) - (t1.remainingMs ?? 0)).toBeCloseTo(HOUR, -3);
  });
});

describe('formatRemaining', () => {
  it('formats future time without the overdue prefix', () => {
    expect(formatRemaining(5 * HOUR + 12 * 60_000)).toBe('5h 12m');
    expect(formatRemaining(2 * 86_400_000 + 3 * HOUR)).toBe('2d 3h');
  });

  it('prefixes overdue for negative remaining', () => {
    expect(formatRemaining(-(3 * HOUR + 5 * 60_000))).toMatch(/^overdue 3h 5m/);
  });

  it('shows minutes and seconds under an hour', () => {
    expect(formatRemaining(42 * 60_000 + 18_000)).toBe('42m 18s');
  });
});
