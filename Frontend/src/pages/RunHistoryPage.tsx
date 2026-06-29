import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { History, RefreshCw, CheckCircle2, ChevronLeft, ChevronRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyRunState } from '@/components/common/EmptyRunState';
import { cn } from '@/lib/utils';
import { useRun } from '@/hooks/useRun';
import type { RunStatus } from '@/lib/api';

const PAGE_SIZE = 12;

const STATUS_FILTERS: { key: 'all' | RunStatus; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'AWAITING_REVIEW', label: 'Awaiting review' },
  { key: 'COMPLETED', label: 'Completed' },
  { key: 'RUNNING', label: 'Running' },
  { key: 'FAILED', label: 'Failed' },
];

function shortId(runId: string): string {
  return runId.replace(/^run_/, '').slice(0, 8);
}

function fmtDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

export function RunHistoryPage() {
  const { history, runId, selectRun, loadRuns, isLoadingData } = useRun();
  const navigate = useNavigate();

  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<'all' | RunStatus>('all');
  const [page, setPage] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return history.filter((r) => {
      if (status !== 'all' && r.status !== status) return false;
      if (q && !r.runId.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [history, query, status]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages - 1);
  const pageItems = filtered.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);

  const open = (id: string) => {
    selectRun(id);
    navigate('/dashboard');
  };

  const refresh = async () => {
    setRefreshing(true);
    try {
      await loadRuns();
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold tracking-tight">Run history</h1>
          <p className="text-muted-foreground mt-1">
            Every exception run you've uploaded. Open one to review its exceptions, SLA, and resolutions.
          </p>
        </div>
        <Button variant="outline" onClick={() => void refresh()} disabled={refreshing} className="gap-2">
          <RefreshCw className={cn('w-4 h-4', refreshing && 'animate-spin')} />
          Refresh
        </Button>
      </div>

      {isLoadingData && history.length === 0 ? (
        <HistorySkeleton />
      ) : history.length === 0 ? (
        <EmptyRunState />
      ) : (
        <Card>
          <CardHeader className="gap-3">
            <CardTitle className="flex items-center gap-2">
              <History className="w-5 h-5 text-primary" />
              All runs
              <Badge variant="secondary" className="ml-1">{filtered.length}</Badge>
            </CardTitle>
            <div className="flex flex-wrap items-center gap-2">
              <Input
                placeholder="Search by run id…"
                value={query}
                onChange={(e) => { setQuery(e.target.value); setPage(0); }}
                className="h-9 max-w-xs"
              />
              <div className="flex flex-wrap gap-1.5">
                {STATUS_FILTERS.map((f) => (
                  <button
                    key={f.key}
                    type="button"
                    onClick={() => { setStatus(f.key); setPage(0); }}
                    className={cn(
                      'rounded-full border px-3 py-1 text-xs font-medium transition-colors',
                      status === f.key
                        ? 'border-primary bg-primary/10 text-primary'
                        : 'border-border text-muted-foreground hover:text-foreground',
                    )}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {/* Header row (md+) */}
            <div className="hidden md:grid grid-cols-[1.3fr_1.6fr_0.8fr_0.8fr_1fr_auto] gap-3 px-3 pb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              <span>Run</span>
              <span>Created</span>
              <span className="text-right">Rows</span>
              <span className="text-right">Quarantined</span>
              <span>Status</span>
              <span className="sr-only">Open</span>
            </div>

            {pageItems.map((r) => {
              const active = r.runId === runId;
              return (
                <div
                  key={r.runId}
                  className={cn(
                    'grid grid-cols-2 md:grid-cols-[1.3fr_1.6fr_0.8fr_0.8fr_1fr_auto] items-center gap-x-3 gap-y-1 rounded-lg border bg-card px-3 py-2.5',
                    active && 'border-primary ring-1 ring-primary/30',
                  )}
                >
                  <span className="flex items-center gap-2 min-w-0">
                    {active && <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-primary" />}
                    <span className="font-mono text-sm truncate">{shortId(r.runId)}</span>
                  </span>
                  <span className="text-sm text-muted-foreground">{fmtDate(r.createdAt)}</span>
                  <span className="text-right text-sm tabular-nums">{r.rowsAccepted}</span>
                  <span className="text-right text-sm tabular-nums">{r.rowsQuarantined}</span>
                  <span>
                    <Badge variant={r.status === 'FAILED' ? 'danger' : 'secondary'}>{r.status}</Badge>
                  </span>
                  <span className="md:justify-self-end">
                    <Button size="sm" variant={active ? 'secondary' : 'outline'} onClick={() => open(r.runId)}>
                      {active ? 'Active' : 'Open'}
                    </Button>
                  </span>
                </div>
              );
            })}

            {filtered.length === 0 && (
              <p className="py-8 text-center text-sm text-muted-foreground">No runs match this filter.</p>
            )}

            {totalPages > 1 && (
              <div className="flex items-center justify-between pt-2">
                <span className="text-xs text-muted-foreground">
                  Page {safePage + 1} of {totalPages}
                </span>
                <div className="flex gap-1">
                  <Button size="sm" variant="outline" disabled={safePage === 0} onClick={() => setPage(safePage - 1)} className="gap-1">
                    <ChevronLeft className="w-4 h-4" /> Prev
                  </Button>
                  <Button size="sm" variant="outline" disabled={safePage >= totalPages - 1} onClick={() => setPage(safePage + 1)} className="gap-1">
                    Next <ChevronRight className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function HistorySkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-6 w-40" />
      </CardHeader>
      <CardContent className="space-y-3">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-11 w-full" />
        ))}
      </CardContent>
    </Card>
  );
}
