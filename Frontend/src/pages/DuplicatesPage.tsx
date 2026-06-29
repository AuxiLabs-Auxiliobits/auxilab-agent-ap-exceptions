import { useCallback, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Copy, AlertTriangle, ShieldCheck, RefreshCw, ArrowRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyRunState } from '@/components/common/EmptyRunState';
import { useRun } from '@/hooks/useRun';
import { api, ApiError, type DuplicatesResponse } from '@/lib/api';

const fmtMoney = (s: string) => {
  const n = Number(s);
  return Number.isFinite(n)
    ? new Intl.NumberFormat(undefined, {
        style: 'currency',
        currency: 'USD',
        maximumFractionDigits: 0,
      }).format(n)
    : s;
};
const shortId = (id: string) => id.replace(/^run_/, '').slice(0, 8);
const shortDate = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
};

export function DuplicatesPage() {
  const { runId } = useRun();
  const [data, setData] = useState<DuplicatesResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!runId) {
      setData(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setData(await api.getDuplicates(runId));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    void load();
  }, [load]);

  const dups = data?.duplicates ?? [];
  const exactDoubles = dups.filter((d) => d.occurrences.some((o) => o.amount_matches)).length;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold tracking-tight">Duplicate Check</h1>
          <p className="text-muted-foreground mt-1">
            Invoices in this run already seen in a previous run — a double-pay guard.
          </p>
        </div>
        {runId && (
          <Button variant="outline" onClick={() => void load()} disabled={loading} className="gap-2">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Recheck
          </Button>
        )}
      </div>

      {!runId ? (
        <EmptyRunState />
      ) : loading && !data ? (
        <DupSkeleton />
      ) : error ? (
        <Card className="border-overdue/30">
          <CardContent className="flex items-start gap-2 text-overdue pt-6">
            <AlertTriangle className="w-5 h-5 mt-0.5 shrink-0" />
            <span className="break-words">{error}</span>
          </CardContent>
        </Card>
      ) : data ? (
        <>
          {/* ---- Summary banner ---- */}
          {dups.length === 0 ? (
            <Card className="border-settled/30">
              <CardContent className="flex items-center gap-3 pt-6 text-settled">
                <ShieldCheck className="w-6 h-6 shrink-0" />
                <div>
                  <p className="font-medium">No historical duplicates.</p>
                  <p className="text-sm text-muted-foreground">
                    Checked {data.checked} invoice{data.checked === 1 ? '' : 's'} against{' '}
                    {data.runs_scanned} prior run{data.runs_scanned === 1 ? '' : 's'}.
                  </p>
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card className="border-overdue/30 bg-overdue/[0.04]">
              <CardContent className="flex items-center gap-3 pt-6">
                <span className="grid h-10 w-10 place-items-center rounded-lg bg-overdue/12 text-overdue shrink-0">
                  <Copy className="w-5 h-5" />
                </span>
                <div>
                  <p className="font-medium text-overdue">
                    {dups.length} possible duplicate{dups.length === 1 ? '' : 's'} found
                    {exactDoubles > 0 &&
                      ` · ${exactDoubles} exact amount match${exactDoubles === 1 ? '' : 'es'}`}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Across {data.runs_scanned} prior run{data.runs_scanned === 1 ? '' : 's'} ·{' '}
                    {data.checked} invoices checked. Review before paying.
                  </p>
                </div>
              </CardContent>
            </Card>
          )}

          {/* ---- Match cards ---- */}
          {dups.length > 0 && (
            <div className="space-y-3">
              {dups.map((d, i) => (
                <motion.div
                  key={d.invoice_id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(i * 0.03, 0.2) }}
                >
                  <Card>
                    <CardHeader className="pb-3">
                      <CardTitle className="flex flex-wrap items-center gap-2 text-base">
                        <span className="font-mono">{d.invoice_id}</span>
                        <span className="font-normal text-muted-foreground">· {d.vendor_name}</span>
                        <span className="ml-auto tabular-nums">{fmtMoney(d.invoice_amount)}</span>
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                        Seen before in {d.occurrences.length} run{d.occurrences.length === 1 ? '' : 's'}
                      </p>
                      <div className="space-y-2">
                        {d.occurrences.map((o) => (
                          <div
                            key={`${o.run_id}-${o.created_at}`}
                            className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border bg-muted/30 px-3 py-2 text-sm"
                          >
                            <ArrowRight className="w-3.5 h-3.5 shrink-0 text-muted-foreground" />
                            <span className="font-mono text-xs">{shortId(o.run_id)}</span>
                            <span className="text-muted-foreground">{shortDate(o.created_at)}</span>
                            <span className="tabular-nums">{fmtMoney(o.invoice_amount)}</span>
                            {o.amount_matches ? (
                              <Badge variant="danger" className="ml-auto">Exact match</Badge>
                            ) : (
                              <Badge variant="warning" className="ml-auto">Amount differs</Badge>
                            )}
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>
              ))}
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}

function DupSkeleton() {
  return (
    <>
      <Card>
        <CardContent className="flex items-center gap-3 pt-6">
          <Skeleton className="h-10 w-10 rounded-lg" />
          <div className="space-y-2">
            <Skeleton className="h-4 w-48" />
            <Skeleton className="h-3 w-64" />
          </div>
        </CardContent>
      </Card>
      {Array.from({ length: 3 }).map((_, i) => (
        <Card key={i}>
          <CardContent className="space-y-3 p-5">
            <Skeleton className="h-5 w-56" />
            <Skeleton className="h-9 w-full" />
          </CardContent>
        </Card>
      ))}
    </>
  );
}
