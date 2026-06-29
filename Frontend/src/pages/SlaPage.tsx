import { useState } from 'react';
import { motion } from 'framer-motion';
import { AlarmClock, ShieldAlert, Clock, CheckCircle2, Timer, Mail, Loader2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyRunState } from '@/components/common/EmptyRunState';
import { useRun } from '@/hooks/useRun';
import { useSla } from '@/hooks/useSla';
import { usePermissions } from '@/hooks/usePermissions';
import { formatRemaining, formatDeadline, type SlaStatus } from '@/lib/sla';
import { api, ApiError, type DigestResult } from '@/lib/api';
import { resolutionPathLabel } from '@/lib/resolutionLabels';
import type { Severity } from '@/types';

const STATUS_META: Record<
  Exclude<SlaStatus, 'unknown'>,
  { label: string; dot: string; ink: string; chip: string }
> = {
  breached: { label: 'Breached', dot: 'bg-overdue', ink: 'text-overdue', chip: 'bg-overdue/12 text-overdue' },
  due_soon: { label: 'Due soon', dot: 'bg-pending', ink: 'text-pending', chip: 'bg-pending/12 text-pending' },
  on_track: { label: 'On track', dot: 'bg-settled', ink: 'text-settled', chip: 'bg-settled/12 text-settled' },
};

const fmtMoney = (n: number) =>
  new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n);

function severityVariant(s: Severity): 'danger' | 'warning' | 'success' {
  return s === 'High' ? 'danger' : s === 'Medium' ? 'warning' : 'success';
}

export function SlaPage() {
  const { runId, isLoadingData } = useRun();
  // 1s tick here for a smooth, live countdown (the sidebar/header use the slow default).
  const { rows, breached, dueSoon, onTrack } = useSla(1000);
  // Resolved / won't-fix cases are off the clock — they live in the Resolution
  // Tracker, not here. The summary counts already exclude them.
  const visibleRows = rows.filter((r) => !r.closed);
  const { can } = usePermissions();
  const canSend = can('comms:send');

  const [digestBusy, setDigestBusy] = useState(false);
  const [digestMsg, setDigestMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

  const sendDigest = async () => {
    if (!runId) return;
    setDigestBusy(true);
    setDigestMsg(null);
    try {
      const res: DigestResult = await api.sendDigest(runId);
      const n = res.notification;
      const s = res.summary;
      if (n.status === 'skipped') {
        setDigestMsg({ kind: 'err', text: `Digest not sent: ${n.reason ?? 'no AP team mailbox configured.'}` });
      } else {
        const verb = n.status === 'dryrun' ? 'Dry-run digest written' : 'Digest sent';
        setDigestMsg({
          kind: 'ok',
          text: `${verb} to ${n.recipient} — ${s.breached} breached, ${s.due_soon} due soon, ${s.needs_follow_up} need follow-up.`,
        });
      }
    } catch (e) {
      setDigestMsg({ kind: 'err', text: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setDigestBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold tracking-tight">SLA Tracker</h1>
          <p className="text-muted-foreground mt-1">
            Open exceptions on the clock — sorted by time to breach. Work the red first.
          </p>
        </div>
        {runId && visibleRows.length > 0 && (
          <Button
            variant="outline"
            onClick={() => void sendDigest()}
            disabled={digestBusy || !canSend}
            title={canSend ? 'Email the AP team an SLA + case digest' : 'Your role cannot send communications'}
            className="gap-2 shrink-0"
          >
            {digestBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Mail className="w-4 h-4" />}
            Email digest
          </Button>
        )}
      </div>

      {digestMsg && (
        <div
          className={`flex items-start gap-2 rounded-lg border p-3 text-sm ${
            digestMsg.kind === 'ok'
              ? 'bg-settled/10 border-settled/20 text-settled'
              : 'bg-overdue/10 border-overdue/20 text-overdue'
          }`}
        >
          {digestMsg.kind === 'ok' ? (
            <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />
          ) : (
            <ShieldAlert className="w-4 h-4 mt-0.5 shrink-0" />
          )}
          <span className="break-words">{digestMsg.text}</span>
        </div>
      )}

      {isLoadingData && visibleRows.length === 0 ? (
        <SlaSkeleton />
      ) : !runId ? (
        <EmptyRunState />
      ) : visibleRows.length === 0 ? (
        <Card className="min-h-[200px] flex items-center justify-center">
          <CardContent className="text-center text-muted-foreground pt-6">
            <CheckCircle2 className="w-10 h-10 mx-auto mb-3 text-settled opacity-80" />
            Nothing on the clock — every exception in this run is auto-cleared, resolved, or has no SLA.
          </CardContent>
        </Card>
      ) : (
        <>
          {/* ---- Summary tiles ---- */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <SummaryTile
              label="Breached"
              value={breached}
              hint="past the deadline"
              icon={ShieldAlert}
              chip="bg-overdue/12 text-overdue"
            />
            <SummaryTile
              label="Due soon"
              value={dueSoon}
              hint="within 4 hours"
              icon={AlarmClock}
              chip="bg-pending/12 text-pending"
            />
            <SummaryTile
              label="On track"
              value={onTrack}
              hint="comfortable headroom"
              icon={Clock}
              chip="bg-settled/12 text-settled"
            />
          </div>

          {/* ---- The clock list ---- */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Timer className="w-5 h-5 text-primary" />
                On the clock
                <Badge variant="secondary" className="ml-1">{visibleRows.length}</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {/* Header row (md+) */}
              <div className="hidden md:grid grid-cols-[1.2fr_1.4fr_0.8fr_1.3fr_0.7fr_1.2fr] gap-3 px-3 pb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                <span>Invoice</span>
                <span>Vendor</span>
                <span className="text-right">Amount</span>
                <span>Resolution</span>
                <span>Severity</span>
                <span className="text-right">Time to breach</span>
              </div>

              {visibleRows.map(({ ex, sla }, i) => {
                const meta = STATUS_META[sla.status as Exclude<SlaStatus, 'unknown'>];
                return (
                  <motion.div
                    key={ex.id}
                    layout
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: Math.min(i * 0.015, 0.2) }}
                    className="grid grid-cols-2 md:grid-cols-[1.2fr_1.4fr_0.8fr_1.3fr_0.7fr_1.2fr] items-center gap-x-3 gap-y-1 rounded-lg border bg-card px-3 py-2.5"
                  >
                    <span className="flex items-center gap-2 min-w-0">
                      <span className={`h-2 w-2 shrink-0 rounded-full ${meta.dot}`} aria-hidden />
                      <span className="font-mono text-sm truncate">{ex.invoiceId}</span>
                    </span>
                    <span className="truncate text-sm">{ex.vendorName}</span>
                    <span className="text-right text-sm tabular-nums md:order-none order-3">
                      {fmtMoney(ex.invoiceAmount)}
                    </span>
                    <span className="truncate text-sm text-muted-foreground md:order-none order-4">
                      {resolutionPathLabel(ex.resolutionPath)}
                    </span>
                    <span className="md:order-none order-2">
                      <Badge variant={severityVariant(ex.severity)}>{ex.severity}</Badge>
                    </span>
                    <span className="text-right md:order-none order-5">
                      <span className={`font-mono text-sm font-semibold ${meta.ink}`}>
                        {formatRemaining(sla.remainingMs ?? 0)}
                      </span>
                      {sla.deadlineMs != null && (
                        <span className="block font-mono text-[10px] text-muted-foreground">
                          {formatDeadline(sla.deadlineMs)}
                        </span>
                      )}
                    </span>
                  </motion.div>
                );
              })}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function SummaryTile({
  label,
  value,
  hint,
  icon: Icon,
  chip,
}: {
  label: string;
  value: number;
  hint: string;
  icon: React.ElementType;
  chip: string;
}) {
  return (
    <Card className="overflow-hidden">
      <CardContent className="p-5">
        <div className="flex items-center justify-between">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
          <span className={`grid h-8 w-8 place-items-center rounded-md ${chip}`}>
            <Icon className="h-4 w-4" aria-hidden />
          </span>
        </div>
        <p className="mt-3 font-mono text-3xl font-medium tabular-nums">{value}</p>
        <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  );
}

function SlaSkeleton() {
  return (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <Card key={i}>
            <CardContent className="p-5">
              <div className="flex items-center justify-between">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="h-8 w-8 rounded-md" />
              </div>
              <Skeleton className="mt-3 h-9 w-12" />
              <Skeleton className="mt-2 h-3 w-24" />
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardContent className="p-4 space-y-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-11 w-full" />
          ))}
        </CardContent>
      </Card>
    </>
  );
}
