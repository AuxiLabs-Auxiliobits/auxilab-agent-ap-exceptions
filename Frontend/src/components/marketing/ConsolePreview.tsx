/**
 * A code-rendered "screenshot" of the LedgerClear console for the marketing page.
 * Pure HTML/CSS (no image asset), theme-aware, and responsive — a faithful
 * preview of the clearing desk: reconciliation strip, KPI tiles, and the live
 * SLA list. Numbers are illustrative (it's a UI preview, not live data).
 */
const NAV = ['Dashboard', 'Exception Queue', 'SLA Tracker', 'Resolution Tracker', 'Analytics'];

const STRIP = [
  { label: 'At risk', pct: 18, bar: 'bg-overdue', ink: 'text-overdue' },
  { label: 'Escalated', pct: 22, bar: 'bg-pending', ink: 'text-pending' },
  { label: 'Awaiting', pct: 30, bar: 'bg-muted-foreground/40', ink: 'text-muted-foreground' },
  { label: 'Cleared', pct: 30, bar: 'bg-settled', ink: 'text-settled' },
];

const TILES = [
  { label: 'Auto-resolvable', value: '2,340', ink: 'text-settled' },
  { label: 'Escalations', value: '86', ink: 'text-pending' },
  { label: 'High severity', value: '27', ink: 'text-overdue' },
  { label: 'Resolution rate', value: '78%', ink: 'text-primary' },
];

const ROWS = [
  { id: 'INV-2001', vendor: 'Halford Logistics', amt: '$182,400', path: 'Escalate', sla: '1h 12m', ink: 'text-overdue', dot: 'bg-overdue' },
  { id: 'INV-2044', vendor: 'Acme Foods', amt: '$12,000', path: 'Request PO', sla: '6h 03m', ink: 'text-pending', dot: 'bg-pending' },
  { id: 'INV-2090', vendor: 'Globex', amt: '$9,400', path: 'Request GRN', sla: '41h', ink: 'text-settled', dot: 'bg-settled' },
];

export function ConsolePreview() {
  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-card shadow-2xl shadow-foreground/[0.10]">
      {/* Window chrome */}
      <div className="flex items-center gap-2 border-b border-border bg-muted/40 px-4 py-2.5">
        <span className="h-2.5 w-2.5 rounded-full bg-overdue/70" />
        <span className="h-2.5 w-2.5 rounded-full bg-pending/70" />
        <span className="h-2.5 w-2.5 rounded-full bg-settled/70" />
        <div className="mx-auto hidden items-center gap-2 rounded-md border border-border bg-background/60 px-3 py-1 font-mono text-[11px] text-muted-foreground sm:flex">
          app.ledgerclear.ai · Clearing desk
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-[176px_1fr]">
        {/* Sidebar (desktop) */}
        <aside className="hidden border-r border-border bg-muted/20 p-3 sm:block">
          <div className="mb-4 flex items-center gap-2">
            <span className="grid h-7 w-7 place-items-center rounded-lg bg-primary text-primary-foreground text-[11px] font-bold">L</span>
            <span className="text-[13px] font-semibold">LedgerClear</span>
          </div>
          <ul className="space-y-1">
            {NAV.map((n, i) => (
              <li
                key={n}
                className={`rounded-md px-2.5 py-1.5 text-[12px] ${
                  i === 2 ? 'bg-primary/10 font-medium text-primary' : 'text-muted-foreground'
                }`}
              >
                {n}
              </li>
            ))}
          </ul>
        </aside>

        {/* Main */}
        <div className="space-y-4 p-4 sm:p-5">
          <div>
            <p className="text-sm font-semibold">Suspended balance · $4.62M</p>
            <p className="text-[11px] text-muted-foreground">by what each dollar is waiting on</p>
          </div>

          {/* Reconciliation strip */}
          <div>
            <div className="flex h-3 w-full overflow-hidden rounded-full">
              {STRIP.map((s) => (
                <div key={s.label} className={s.bar} style={{ width: `${s.pct}%` }} />
              ))}
            </div>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
              {STRIP.map((s) => (
                <span key={s.label} className="flex items-center gap-1.5 text-[11px]">
                  <span className={`h-1.5 w-1.5 rounded-full ${s.bar}`} />
                  <span className="text-muted-foreground">{s.label}</span>
                  <span className={`font-medium ${s.ink}`}>{s.pct}%</span>
                </span>
              ))}
            </div>
          </div>

          {/* KPI tiles */}
          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
            {TILES.map((t) => (
              <div key={t.label} className="rounded-lg border border-border bg-background/60 p-2.5">
                <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{t.label}</p>
                <p className={`mt-1 font-mono text-lg font-medium tabular-nums ${t.ink}`}>{t.value}</p>
              </div>
            ))}
          </div>

          {/* SLA list */}
          <div className="rounded-xl border border-border">
            <div className="flex items-center justify-between border-b border-border px-3 py-2">
              <p className="text-[12px] font-medium">On the clock</p>
              <p className="text-[10px] text-muted-foreground">sorted by time to breach</p>
            </div>
            <div className="divide-y divide-border">
              {ROWS.map((r) => (
                <div key={r.id} className="flex items-center gap-3 px-3 py-2 text-[12px]">
                  <span className={`h-2 w-2 shrink-0 rounded-full ${r.dot}`} />
                  <span className="font-mono">{r.id}</span>
                  <span className="hidden truncate text-muted-foreground sm:inline">{r.vendor}</span>
                  <span className="ml-auto tabular-nums">{r.amt}</span>
                  <span className="hidden w-24 text-right text-muted-foreground md:inline">{r.path}</span>
                  <span className={`w-16 text-right font-mono font-semibold ${r.ink}`}>{r.sla}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
