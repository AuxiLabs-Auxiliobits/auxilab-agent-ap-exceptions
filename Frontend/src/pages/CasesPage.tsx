import { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { CircleDot, Loader2, CheckCircle2, BellRing, RefreshCw, X } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { EmptyRunState } from '@/components/common/EmptyRunState';
import { useRun } from '@/hooks/useRun';
import { useSla } from '@/hooks/useSla';
import { usePermissions } from '@/hooks/usePermissions';
import { formatRemaining } from '@/lib/sla';
import { cn } from '@/lib/utils';
import { ApiError, type CaseStatus } from '@/lib/api';
import { resolutionPathLabel } from '@/lib/resolutionLabels';

const STATUS_OPTIONS: { value: CaseStatus; label: string }[] = [
  { value: 'OPEN', label: 'Open' },
  { value: 'IN_PROGRESS', label: 'In progress' },
  { value: 'RESOLVED', label: 'Resolved' },
  { value: 'WONT_FIX', label: "Won't fix" },
];
const STATUS_LABEL: Record<CaseStatus, string> = {
  OPEN: 'Open',
  IN_PROGRESS: 'In progress',
  RESOLVED: 'Resolved',
  WONT_FIX: "Won't fix",
};
function statusVariant(s: CaseStatus): 'secondary' | 'warning' | 'success' {
  return s === 'RESOLVED' ? 'success' : s === 'IN_PROGRESS' ? 'warning' : 'secondary';
}

type FilterKey = 'all' | 'followup' | 'OPEN' | 'IN_PROGRESS' | 'CLOSED';
const FILTERS: { key: FilterKey; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'followup', label: 'Needs follow-up' },
  { key: 'OPEN', label: 'Open' },
  { key: 'IN_PROGRESS', label: 'In progress' },
  { key: 'CLOSED', label: 'Closed' },
];

const fmtMoney = (n: number) =>
  new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n);

const isClosed = (s: CaseStatus) => s === 'RESOLVED' || s === 'WONT_FIX';

export function CasesPage() {
  // Cases live in the shared run store, so a status change here flows straight to
  // the Dashboard, SLA Tracker, sidebar badges, and the queues — no stale views.
  const { runId, isLoadingData, cases, updateCaseStatus, reloadData } = useRun();
  const { rows } = useSla(); // actionable exceptions + live SLA
  const { can } = usePermissions();
  const canEdit = can('draft:edit');

  const [refreshing, setRefreshing] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterKey>('all');
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const refresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      await reloadData();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setRefreshing(false);
    }
  };

  const changeStatus = async (invoiceId: string, status: CaseStatus) => {
    if (!runId) return;
    setBusyId(invoiceId);
    setError(null);
    try {
      await updateCaseStatus(invoiceId, status);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  const items = useMemo(() => {
    const joined = rows.map(({ ex, sla }) => {
      const status: CaseStatus = cases[ex.invoiceId]?.status ?? 'OPEN';
      const needsFollowUp = !isClosed(status) && sla.status === 'breached';
      return { ex, sla, status, needsFollowUp, note: cases[ex.invoiceId]?.note ?? null };
    });
    const rank = (it: (typeof joined)[number]) =>
      it.needsFollowUp ? 0 : it.status === 'OPEN' ? 1 : it.status === 'IN_PROGRESS' ? 2 : 3;
    return [...joined].sort(
      (a, b) => rank(a) - rank(b) || (a.sla.remainingMs ?? 0) - (b.sla.remainingMs ?? 0),
    );
  }, [rows, cases]);

  const counts = useMemo(() => {
    let open = 0;
    let inProgress = 0;
    let resolved = 0;
    let followUp = 0;
    for (const it of items) {
      if (isClosed(it.status)) resolved++;
      else if (it.status === 'IN_PROGRESS') inProgress++;
      else open++;
      if (it.needsFollowUp) followUp++;
    }
    return { open, inProgress, resolved, followUp };
  }, [items]);

  const filtered = useMemo(() => {
    switch (filter) {
      case 'followup':
        return items.filter((it) => it.needsFollowUp);
      case 'OPEN':
        return items.filter((it) => it.status === 'OPEN');
      case 'IN_PROGRESS':
        return items.filter((it) => it.status === 'IN_PROGRESS');
      case 'CLOSED':
        return items.filter((it) => isClosed(it.status));
      default:
        return items;
    }
  }, [items, filter]);

  // Selecting / bulk-applying operates on the (editable) filtered view.
  const filteredIds = useMemo(
    () => filtered.map((it) => it.ex.invoiceId).filter((v): v is string => Boolean(v)),
    [filtered],
  );
  const allSelected = filteredIds.length > 0 && filteredIds.every((id) => selected.has(id));

  const toggleAll = () =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (filteredIds.every((id) => next.has(id))) filteredIds.forEach((id) => next.delete(id));
      else filteredIds.forEach((id) => next.add(id));
      return next;
    });

  const toggleOne = (id: string, on: boolean) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });

  const applyBulk = async (status: CaseStatus) => {
    if (!runId || selected.size === 0) return;
    const ids = [...selected];
    setBulkBusy(true);
    setError(null);
    const results = await Promise.allSettled(ids.map((id) => updateCaseStatus(id, status)));
    const failures = results.filter((r) => r.status === 'rejected').length;
    setSelected(new Set());
    setBulkBusy(false);
    if (failures > 0) setError(`${failures} of ${ids.length} update(s) failed.`);
  };

  const setFilterToggle = (key: FilterKey) => setFilter((f) => (f === key ? 'all' : key));

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold tracking-tight">Resolution Tracker</h1>
          <p className="text-muted-foreground mt-1">
            Drive every exception to closure — Open → In progress → Resolved. Overdue items surface
            for follow-up.
          </p>
        </div>
        {runId && (
          <Button variant="outline" onClick={() => void refresh()} disabled={refreshing || isLoadingData} className="gap-2">
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        )}
      </div>

      {error && (
        <Card className="border-overdue/30">
          <CardContent className="pt-4 text-sm text-overdue break-words">{error}</CardContent>
        </Card>
      )}

      {!runId ? (
        <EmptyRunState />
      ) : isLoadingData && items.length === 0 ? (
        <TrackerSkeleton />
      ) : items.length === 0 ? (
        <Card className="min-h-[160px] flex items-center justify-center">
          <CardContent className="text-center text-muted-foreground pt-6">
            Nothing to track — this run has no exceptions that need human resolution.
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <SummaryTile label="Needs follow-up" value={counts.followUp} icon={BellRing} chip="bg-overdue/12 text-overdue" active={filter === 'followup'} onClick={() => setFilterToggle('followup')} />
            <SummaryTile label="Open" value={counts.open} icon={CircleDot} chip="bg-muted text-muted-foreground" active={filter === 'OPEN'} onClick={() => setFilterToggle('OPEN')} />
            <SummaryTile label="In progress" value={counts.inProgress} icon={Loader2} chip="bg-pending/12 text-pending" active={filter === 'IN_PROGRESS'} onClick={() => setFilterToggle('IN_PROGRESS')} />
            <SummaryTile label="Resolved" value={counts.resolved} icon={CheckCircle2} chip="bg-settled/12 text-settled" active={filter === 'CLOSED'} onClick={() => setFilterToggle('CLOSED')} />
          </div>

          {/* Filter chips */}
          <div className="flex flex-wrap items-center gap-2">
            {FILTERS.map((f) => (
              <button
                key={f.key}
                type="button"
                onClick={() => setFilter(f.key)}
                className={cn(
                  'rounded-full border px-3 py-1 text-xs font-medium transition-colors',
                  filter === f.key
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border text-muted-foreground hover:text-foreground',
                )}
              >
                {f.label}
              </button>
            ))}
            <span className="ml-auto text-xs text-muted-foreground">
              {filtered.length} of {items.length}
            </span>
          </div>

          {/* Bulk action bar */}
          {canEdit && selected.size > 0 && (
            <div className="flex flex-wrap items-center gap-2 rounded-lg border border-primary/30 bg-primary/[0.06] px-3 py-2">
              <span className="text-sm font-medium">{selected.size} selected</span>
              <span className="text-xs text-muted-foreground">· set all to</span>
              {STATUS_OPTIONS.map((o) => (
                <Button
                  key={o.value}
                  size="sm"
                  variant="outline"
                  disabled={bulkBusy}
                  onClick={() => void applyBulk(o.value)}
                  className="h-7 gap-1"
                >
                  {bulkBusy && <Loader2 className="h-3 w-3 animate-spin" />}
                  {o.label}
                </Button>
              ))}
              <Button size="sm" variant="ghost" disabled={bulkBusy} onClick={() => setSelected(new Set())} className="h-7 ml-auto gap-1">
                <X className="h-3.5 w-3.5" /> Clear
              </Button>
            </div>
          )}

          {/* Select-all (filtered) */}
          {canEdit && filtered.length > 0 && (
            <label className="flex items-center gap-2 px-1 text-xs text-muted-foreground">
              <Checkbox checked={allSelected} onCheckedChange={toggleAll} />
              Select all {filter === 'all' ? '' : 'filtered '}({filteredIds.length})
            </label>
          )}

          <div className="space-y-2">
            {filtered.map(({ ex, sla, status, needsFollowUp, note }, i) => {
              const id = ex.invoiceId ?? ex.id;
              return (
                <motion.div
                  key={ex.id}
                  layout
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(i * 0.015, 0.2) }}
                  className={cn('rounded-lg border bg-card px-3 py-2.5', needsFollowUp && 'border-overdue/40')}
                >
                  <div className="flex items-start gap-3">
                    {canEdit && (
                      <Checkbox
                        className="mt-1 shrink-0"
                        checked={selected.has(id)}
                        onCheckedChange={(v) => toggleOne(id, v === true)}
                        aria-label={`Select ${id}`}
                      />
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="grid grid-cols-1 md:grid-cols-[1.1fr_1.3fr_0.8fr_1.2fr_1fr_auto] items-center gap-x-3 gap-y-1.5">
                        <span className="flex items-center gap-2 min-w-0">
                          {needsFollowUp && <BellRing className="h-3.5 w-3.5 shrink-0 text-overdue" />}
                          <span className="font-mono text-sm truncate">{ex.invoiceId}</span>
                        </span>
                        <span className="truncate text-sm">{ex.vendorName}</span>
                        <span className="text-sm tabular-nums">{fmtMoney(ex.invoiceAmount)}</span>
                        <span className="truncate text-sm text-muted-foreground">
                          {resolutionPathLabel(ex.resolutionPath)}
                        </span>
                        <span className="text-sm">
                          {isClosed(status) ? (
                            <span className="text-muted-foreground">—</span>
                          ) : (
                            <span className={cn('font-mono', sla.status === 'breached' ? 'text-overdue font-semibold' : sla.status === 'due_soon' ? 'text-pending' : 'text-muted-foreground')}>
                              {formatRemaining(sla.remainingMs ?? 0)}
                            </span>
                          )}
                        </span>
                        <span className="md:justify-self-end">
                          {canEdit ? (
                            <Select
                              value={status}
                              onValueChange={(v) => void changeStatus(id, v as CaseStatus)}
                              disabled={busyId === id || bulkBusy}
                            >
                              <SelectTrigger className="h-8 w-36 text-xs">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                {STATUS_OPTIONS.map((o) => (
                                  <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          ) : (
                            <Badge variant={statusVariant(status)}>{STATUS_LABEL[status]}</Badge>
                          )}
                        </span>
                      </div>
                      {note && <p className="mt-1.5 text-xs text-muted-foreground">Note: {note}</p>}
                    </div>
                  </div>
                </motion.div>
              );
            })}
            {filtered.length === 0 && (
              <p className="py-8 text-center text-sm text-muted-foreground">
                No cases match this filter.
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function SummaryTile({
  label,
  value,
  icon: Icon,
  chip,
  active,
  onClick,
}: {
  label: string;
  value: number;
  icon: React.ElementType;
  chip: string;
  active?: boolean;
  onClick?: () => void;
}) {
  return (
    <button type="button" onClick={onClick} className="text-left">
      <Card className={cn('overflow-hidden transition-colors hover:border-primary/40', active && 'border-primary ring-1 ring-primary/30')}>
        <CardContent className="p-4">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
            <span className={cn('grid h-8 w-8 place-items-center rounded-md', chip)}>
              <Icon className="h-4 w-4" aria-hidden />
            </span>
          </div>
          <p className="mt-2 font-mono text-2xl font-medium tabular-nums">{value}</p>
        </CardContent>
      </Card>
    </button>
  );
}

function TrackerSkeleton() {
  return (
    <>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i}>
            <CardContent className="p-4">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="mt-3 h-7 w-10" />
            </CardContent>
          </Card>
        ))}
      </div>
      {Array.from({ length: 6 }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </>
  );
}
