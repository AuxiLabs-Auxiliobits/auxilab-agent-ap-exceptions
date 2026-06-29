import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Building2, AlertCircle, RefreshCw, ShieldCheck, Mail, Search,
  ChevronLeft, ChevronRight,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { VendorContactsPanel } from '@/components/vendors/VendorContactsPanel';
import { cn } from '@/lib/utils';
import { api, ApiError, type VendorProfile } from '@/lib/api';

const PAGE_SIZE = 12;

function reliabilityBadge(score: number) {
  if (score >= 0.7) return <Badge variant="success">Reliable</Badge>;
  if (score >= 0.4) return <Badge variant="warning">Watch</Badge>;
  return <Badge variant="danger">Risky</Badge>;
}

type TabKey = 'directory' | 'reliability';

/**
 * Vendors — two distinct concerns split into tabs so neither clutters the other:
 *   • Email directory: editable vendor→AR-email map that drives routing.
 *   • Reliability:     read-only longitudinal profiles accumulated across runs.
 * Both get search; large lists paginate so 1000+ vendors stay usable.
 */
export function VendorsPage() {
  const [params, setParams] = useSearchParams();
  const tab: TabKey = params.get('tab') === 'reliability' ? 'reliability' : 'directory';

  const setTab = (next: TabKey) => {
    const p = new URLSearchParams(params);
    if (next === 'directory') p.delete('tab');
    else p.set('tab', next);
    setParams(p, { replace: true });
  };

  const tabs: { key: TabKey; label: string; icon: typeof Mail }[] = [
    { key: 'directory', label: 'Email Directory', icon: Mail },
    { key: 'reliability', label: 'Reliability', icon: ShieldCheck },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold tracking-tight">Vendors</h1>
          <p className="text-muted-foreground mt-1">
            {tab === 'reliability'
              ? 'Longitudinal vendor reliability profiles, accumulated across runs.'
              : 'Map each vendor to its AR email so invoices route to the right inbox.'}
          </p>
        </div>

        <div className="inline-flex rounded-lg border bg-card p-1" role="tablist" aria-label="Vendors view">
          {tabs.map((t) => {
            const active = tab === t.key;
            return (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setTab(t.key)}
                className={cn(
                  'inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                  active ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:text-foreground',
                )}
              >
                <t.icon className="h-4 w-4" />
                {t.label}
              </button>
            );
          })}
        </div>
      </div>

      {tab === 'directory' ? <VendorContactsPanel /> : <ReliabilityTab />}
    </div>
  );
}

function ReliabilityTab() {
  const [vendors, setVendors] = useState<VendorProfile[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(0);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.listVendors();
      setVendors(res.profiles);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setVendors(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!vendors) return [];
    if (!q) return vendors;
    return vendors.filter((v) => v.vendor_name.toLowerCase().includes(q));
  }, [vendors, query]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages - 1);
  const pageItems = filtered.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="relative w-full max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search vendor…"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setPage(0); }}
            className="pl-9 h-9"
          />
        </div>
        <Button variant="outline" onClick={load} disabled={loading} className="gap-2">
          <RefreshCw className={cn('w-4 h-4', loading && 'animate-spin')} />
          Refresh
        </Button>
      </div>

      {loading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => <VendorCardSkeleton key={i} />)}
        </div>
      )}

      {error && !loading && (
        <Card className="border-overdue/30">
          <CardContent className="flex items-start gap-2 text-overdue pt-6">
            <AlertCircle className="w-5 h-5 mt-0.5 shrink-0" />
            <span className="break-words">{error}</span>
          </CardContent>
        </Card>
      )}

      {vendors && !loading && vendors.length === 0 && (
        <Card className="min-h-[200px] flex items-center justify-center">
          <CardContent className="text-center text-muted-foreground pt-6">
            <Building2 className="w-10 h-10 mx-auto mb-3 opacity-50" />
            No vendor history yet. Profiles build up as you process runs.
          </CardContent>
        </Card>
      )}

      {vendors && !loading && vendors.length > 0 && (
        <>
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>{filtered.length} of {vendors.length} vendors</span>
            {totalPages > 1 && <span>Page {safePage + 1} of {totalPages}</span>}
          </div>

          {pageItems.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">No vendors match “{query}”.</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {pageItems.map((v, i) => {
                const score = Math.round(v.reliability_score * 100);
                return (
                  <motion.div
                    key={v.vendor_name}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: Math.min(i * 0.02, 0.15) }}
                  >
                    <Card className="h-full">
                      <CardHeader className="pb-3">
                        <CardTitle className="flex items-center justify-between gap-2 text-base">
                          <span className="flex items-center gap-2 min-w-0">
                            <Building2 className="w-4 h-4 text-primary shrink-0" />
                            <span className="truncate">{v.vendor_name}</span>
                          </span>
                          {reliabilityBadge(v.reliability_score)}
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-3">
                        <div>
                          <div className="flex items-center justify-between text-xs mb-1">
                            <span className="text-muted-foreground flex items-center gap-1">
                              <ShieldCheck className="w-3 h-3" /> Reliability
                            </span>
                            <span className="font-semibold">{score}%</span>
                          </div>
                          <Progress value={score} className="h-2" />
                        </div>

                        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                          <Stat label="Invoices seen" value={v.total_invoices_seen} />
                          <Stat label="Auto-approved" value={v.auto_approved_count} />
                          <Stat label="Escalated" value={v.escalated_count} />
                          <Stat label="Duplicates" value={v.duplicate_count} />
                          <Stat label="Missing PO" value={v.missing_po_count} />
                          <Stat label="Unapproved" value={v.unapproved_vendor_count} />
                        </div>

                        <p className="text-xs text-muted-foreground pt-1">
                          Avg {Math.round(v.average_days_outstanding)}d outstanding ·{' '}
                          {Math.round(v.average_confidence * 100)}% avg confidence
                        </p>
                      </CardContent>
                    </Card>
                  </motion.div>
                );
              })}
            </div>
          )}

          {totalPages > 1 && (
            <div className="flex items-center justify-end gap-1">
              <Button size="sm" variant="outline" disabled={safePage === 0} onClick={() => setPage(safePage - 1)} className="gap-1">
                <ChevronLeft className="w-4 h-4" /> Prev
              </Button>
              <Button size="sm" variant="outline" disabled={safePage >= totalPages - 1} onClick={() => setPage(safePage + 1)} className="gap-1">
                Next <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}

function VendorCardSkeleton() {
  return (
    <Card className="h-full">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between gap-2">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-5 w-16 rounded-full" />
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <Skeleton className="h-2 w-full" />
        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-4 w-full" />)}
        </div>
        <Skeleton className="h-3 w-2/3" />
      </CardContent>
    </Card>
  );
}
