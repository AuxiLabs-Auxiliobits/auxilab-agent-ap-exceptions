/**
 * ReconciliationStrip — the product's signature element.
 *
 * Reframes the whole console from "dashboard of cards" to "a ledger you are
 * clearing": all suspended money rendered as ONE horizontal clearing bar,
 * partitioned by where each dollar sits in its lifecycle. It answers the AP
 * controller's only real question in a glance — *how much is stuck, and what
 * is it waiting on?*
 *
 * Buckets are mutually exclusive and derived honestly from per-exception data
 * (no fabricated figures):
 *   • At risk        — uncleared + High severity  (red ink)
 *   • Escalated      — uncleared, routed to a human controller  (ochre)
 *   • Awaiting review — uncleared, in the queue  (ink / neutral)
 *   • Cleared        — auto-resolved or resolved  (verdigris / settled)
 */
import { useMemo } from 'react';
import { Scale, AlertTriangle, ArrowUp, Clock, CheckCircle2, type LucideIcon } from 'lucide-react';
import { formatCompactCurrency, formatCurrencyFull } from '@/lib/format';
import type { Exception } from '@/types';

interface ReconciliationStripProps {
  exceptions: Exception[];
  /** Average classifier confidence for the run (0–1), shown as ledger context. */
  averageConfidence?: number;
  className?: string;
}

type SegmentKey = 'atRisk' | 'escalated' | 'review' | 'cleared';

interface Segment {
  key: SegmentKey;
  label: string;
  icon: LucideIcon;
  /** Bar fill — a subtle vertical gradient in the segment's tone. */
  bar: string;
  /** Legend icon-chip classes (tinted bg + ring in-tone). */
  chip: string;
  /** Text color for the icon + amount. */
  ink: string;
  amount: number;
  count: number;
}

const CLEARED_STATUSES = new Set(['Auto-Resolved', 'Resolved']);

export function ReconciliationStrip({
  exceptions,
  averageConfidence,
  className,
}: ReconciliationStripProps) {
  const { segments, total, totalCount } = useMemo(() => {
    const acc: Record<SegmentKey, { amount: number; count: number }> = {
      atRisk: { amount: 0, count: 0 },
      escalated: { amount: 0, count: 0 },
      review: { amount: 0, count: 0 },
      cleared: { amount: 0, count: 0 },
    };

    for (const e of exceptions) {
      const amt = e.invoiceAmount || 0;
      let key: SegmentKey;
      if (CLEARED_STATUSES.has(e.status)) key = 'cleared';
      else if (e.severity === 'High') key = 'atRisk';
      else if (e.status === 'Escalated') key = 'escalated';
      else key = 'review';
      acc[key].amount += amt;
      acc[key].count += 1;
    }

    const ordered: Segment[] = [
      { key: 'atRisk', label: 'At risk', icon: AlertTriangle, bar: 'bg-gradient-to-b from-overdue to-overdue/80', chip: 'bg-overdue/12 ring-overdue/30', ink: 'text-overdue', ...acc.atRisk },
      { key: 'escalated', label: 'Escalated', icon: ArrowUp, bar: 'bg-gradient-to-b from-pending to-pending/80', chip: 'bg-pending/12 ring-pending/30', ink: 'text-pending', ...acc.escalated },
      { key: 'review', label: 'Awaiting review', icon: Clock, bar: 'bg-gradient-to-b from-review to-review/80', chip: 'bg-review/12 ring-review/30', ink: 'text-review', ...acc.review },
      { key: 'cleared', label: 'Cleared', icon: CheckCircle2, bar: 'bg-gradient-to-b from-settled to-settled/80', chip: 'bg-settled/12 ring-settled/30', ink: 'text-settled', ...acc.cleared },
    ];

    const total = ordered.reduce((s, seg) => s + seg.amount, 0);
    const totalCount = ordered.reduce((s, seg) => s + seg.count, 0);
    return { segments: ordered, total, totalCount };
  }, [exceptions]);

  const isEmpty = totalCount === 0 || total === 0;

  return (
    <section
      className={`overflow-hidden rounded-lg border bg-card text-card-foreground shadow-[0_1px_2px_hsl(var(--ink)/0.04)] ${className ?? ''}`}
      aria-label="Reconciliation summary"
    >
      {/* ---- Statement header ------------------------------------------------ */}
      <div className="flex flex-wrap items-center justify-between gap-4 px-5 pt-5 pb-4">
        <div className="flex items-center gap-3">
          <span className="grid place-items-center h-10 w-10 rounded-md bg-ink text-ink-foreground ring-1 ring-white/10 shrink-0">
            <Scale className="h-5 w-5" aria-hidden />
          </span>
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              Suspended balance
            </p>
            <p
              className="font-display text-3xl sm:text-4xl font-semibold leading-none tracking-tight tabular-nums"
              title={isEmpty ? undefined : formatCurrencyFull(total)}
            >
              {isEmpty ? '—' : formatCompactCurrency(total)}
            </p>
          </div>
        </div>

        <dl className="flex items-center gap-2 font-mono">
          <Stat label="Exceptions" value={String(totalCount)} />
          {typeof averageConfidence === 'number' && (
            <Stat label="Avg confidence" value={`${Math.round(averageConfidence * 100)}%`} />
          )}
        </dl>
      </div>

      {/* ---- The clearing bar ----------------------------------------------- */}
      {isEmpty ? (
        <div className="mx-5 mb-5 h-9 rounded-md border border-dashed ledger-rule grid place-items-center">
          <p className="font-mono text-xs text-muted-foreground">
            No balance in suspension — upload a queue to begin clearing
          </p>
        </div>
      ) : (
        <div className="mx-5 mb-4 flex h-9 overflow-hidden rounded-md ring-1 ring-border ring-inset">
          {segments
            .filter((s) => s.amount > 0)
            .map((seg) => {
              const pct = (seg.amount / total) * 100;
              return (
                // Plain div: width is explicit so the fill is ALWAYS visible.
                // `animate-grow-x` adds a CSS scaleX entrance whose resting
                // state is fully grown (and which snaps under reduced-motion).
                <div
                  key={seg.key}
                  className={`relative h-full animate-grow-x transition-opacity hover:opacity-90 ${seg.bar}`}
                  style={{ width: `${pct}%`, minWidth: pct < 4 ? '0.5rem' : undefined }}
                  title={`${seg.label}: ${formatCurrencyFull(seg.amount)} · ${seg.count} item${seg.count === 1 ? '' : 's'}`}
                />
              );
            })}
        </div>
      )}

      {/* ---- Ledger legend (icon stat columns) ------------------------------- */}
      <div className="grid grid-cols-2 gap-px border-t bg-border sm:grid-cols-4">
        {segments.map((seg) => {
          const Icon = seg.icon;
          const pct = total > 0 ? Math.round((seg.amount / total) * 100) : 0;
          const dim = seg.amount === 0;
          return (
            <div
              key={seg.key}
              className="group min-w-0 bg-card px-4 py-4 transition-colors hover:bg-muted/30"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span
                    className={`grid h-7 w-7 shrink-0 place-items-center rounded-full ring-1 ${dim ? 'ring-border' : seg.chip}`}
                  >
                    <Icon
                      className={`h-3.5 w-3.5 ${dim ? 'text-muted-foreground/50' : seg.ink}`}
                      aria-hidden
                    />
                  </span>
                  <span className="truncate text-xs font-medium text-muted-foreground">
                    {seg.label}
                  </span>
                </div>
                {/* Prominent share % */}
                <span className={`font-mono text-xs font-semibold tabular-nums ${dim ? 'text-muted-foreground/50' : seg.ink}`}>
                  {pct}%
                </span>
              </div>
              <p
                className={`mt-2 font-mono text-lg font-medium tabular-nums ${dim ? 'text-muted-foreground/50' : seg.ink}`}
                title={formatCurrencyFull(seg.amount)}
              >
                {formatCompactCurrency(seg.amount)}
              </p>
              {/* Mini share bar — visualises this segment's % of the balance. */}
              <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-muted">
                <div className={`h-full rounded-full ${seg.bar}`} style={{ width: `${pct}%` }} />
              </div>
              <p className="mt-1 font-mono text-[11px] text-muted-foreground tabular-nums">
                {seg.count} item{seg.count === 1 ? '' : 's'}
              </p>
            </div>
          );
        })}
      </div>
    </section>
  );
}

/** Small bordered stat chip used in the statement header. */
function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-background/40 px-3 py-1.5 text-right">
      <dt className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</dt>
      <dd className="text-base font-medium text-foreground tabular-nums">{value}</dd>
    </div>
  );
}
