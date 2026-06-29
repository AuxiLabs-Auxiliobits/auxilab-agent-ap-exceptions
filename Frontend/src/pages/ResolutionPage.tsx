import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import {
  CheckCircle2,
  Clock,
  Users,
  GitBranch,
  FileText,
  ShieldCheck,
  AlertCircle,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useRun } from '@/hooks/useRun';
import { api, type ResolutionPathEnum } from '@/lib/api';
import { RESOLUTION_PATH_LABELS } from '@/lib/resolutionLabels';

/**
 * The deterministic resolution catalogue — the seven canonical paths the rules
 * engine can assign. SLA + outreach come from the org's *effective* rulebook
 * (fetched live, admin-visible) so a rule change is reflected immediately;
 * otherwise they fall back to the value observed in the current run, then to the
 * platform default. The per-path count is always from the current run.
 */
type Tone = 'settled' | 'pending' | 'overdue' | 'review';

interface PathMeta {
  label: string;
  description: string;
  defaultSla: number; // hours, from the platform default policy
  comms: boolean | 'varies';
  tone: Tone;
  icon: React.ElementType;
}

// label comes from the shared canonical map (resolutionLabels.ts); this catalogue
// only owns the per-path metadata (description, SLA, comms, tone, icon).
const PATHS: { key: ResolutionPathEnum; meta: PathMeta }[] = [
  { key: 'ESCALATE_CONTROLLER', meta: { label: RESOLUTION_PATH_LABELS.ESCALATE_CONTROLLER, description: 'Sent to a finance controller to decide — material variance or high exposure.', defaultSla: 8, comms: true, tone: 'overdue', icon: Users } },
  { key: 'HOLD_INVESTIGATION', meta: { label: RESOLUTION_PATH_LABELS.HOLD_INVESTIGATION, description: 'Frozen pending review — e.g. a suspected duplicate.', defaultSla: 24, comms: false, tone: 'overdue', icon: Clock } },
  { key: 'REQUEST_PO', meta: { label: RESOLUTION_PATH_LABELS.REQUEST_PO, description: 'Ask the vendor to supply the missing purchase order.', defaultSla: 48, comms: true, tone: 'pending', icon: GitBranch } },
  { key: 'REQUEST_GRN', meta: { label: RESOLUTION_PATH_LABELS.REQUEST_GRN, description: 'Get the goods-receipt confirmation for the billed quantity.', defaultSla: 48, comms: true, tone: 'pending', icon: FileText } },
  { key: 'VENDOR_VALIDATION_REVIEW', meta: { label: RESOLUTION_PATH_LABELS.VENDOR_VALIDATION_REVIEW, description: 'Verify and approve the vendor before proceeding.', defaultSla: 24, comms: true, tone: 'pending', icon: ShieldCheck } },
  { key: 'MANUAL_REVIEW', meta: { label: RESOLUTION_PATH_LABELS.MANUAL_REVIEW, description: 'A human must look — low confidence, or the safe catch-all.', defaultSla: 72, comms: 'varies', tone: 'review', icon: AlertCircle } },
  { key: 'AUTO_APPROVE', meta: { label: RESOLUTION_PATH_LABELS.AUTO_APPROVE, description: 'Cleared automatically — tiny variance and a small amount.', defaultSla: 24, comms: false, tone: 'settled', icon: CheckCircle2 } },
];

const chipClass: Record<Tone, string> = {
  settled: 'bg-settled/12 text-settled',
  pending: 'bg-pending/12 text-pending',
  overdue: 'bg-overdue/12 text-overdue',
  review: 'bg-muted text-muted-foreground',
};
const borderClass: Record<Tone, string> = {
  settled: 'border-settled/20',
  pending: 'border-pending/20',
  overdue: 'border-overdue/20',
  review: 'border-border',
};

// Minimal shape of the rulebook document we read.
interface PolicyDoc {
  version?: string;
  rules?: { then?: { resolution_path?: string; sla_hours?: number; requires_communication?: boolean } }[];
}

export function ResolutionPage() {
  const { results, runId } = useRun();

  // The org's effective rulebook (admin-visible). Best-effort: non-admins get a
  // 403, which we swallow and fall back to run-observed / default values.
  const [policy, setPolicy] = useState<{ map: Map<string, { sla: number; comms: boolean }>; isCustom: boolean } | null>(null);
  useEffect(() => {
    let alive = true;
    api
      .getRules()
      .then((res) => {
        if (!alive) return;
        const doc = res.policy as PolicyDoc;
        const map = new Map<string, { sla: number; comms: boolean }>();
        for (const rule of doc.rules ?? []) {
          const t = rule.then;
          if (!t?.resolution_path || map.has(t.resolution_path)) continue;
          map.set(t.resolution_path, { sla: t.sla_hours ?? 0, comms: !!t.requires_communication });
        }
        setPolicy({ map, isCustom: res.is_custom });
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  // Per-path live count + the SLA / comms observed in this run (a fallback when
  // the live policy isn't available, e.g. for a non-admin viewer).
  const runStats = useMemo(() => {
    const m = new Map<string, { count: number; sla?: number; comms?: boolean }>();
    for (const r of results) {
      const res = r.resolution;
      if (!res) continue;
      const cur = m.get(res.resolution_path) ?? { count: 0 };
      cur.count += 1;
      cur.sla = res.sla_hours;
      cur.comms = res.requires_communication;
      m.set(res.resolution_path, cur);
    }
    return m;
  }, [results]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold tracking-tight">
          Resolution Paths
          {policy?.isCustom && (
            <Badge variant="success" className="ml-3 align-middle">Custom rulebook</Badge>
          )}
        </h1>
        <p className="text-muted-foreground mt-1">
          The deterministic outcomes the rules engine can assign — SLA and outreach reflect your
          effective rulebook{runId ? '; counts are from the current run' : ''}.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {PATHS.map(({ key, meta }, index) => {
          const fromPolicy = policy?.map.get(key);
          const fromRun = runStats.get(key);
          const sla = fromPolicy?.sla ?? fromRun?.sla ?? meta.defaultSla;
          const comms = fromPolicy?.comms ?? fromRun?.comms ?? meta.comms;
          const count = fromRun?.count ?? 0;
          const Icon = meta.icon;
          return (
            <motion.div
              key={key}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.06 }}
            >
              <Card className={`h-full ${borderClass[meta.tone]}`}>
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center gap-3">
                    <div className={`grid h-12 w-12 place-items-center rounded-xl ${chipClass[meta.tone]}`}>
                      <Icon className="w-6 h-6" />
                    </div>
                    <span className="text-base leading-tight">{meta.label}</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-sm text-muted-foreground">{meta.description}</p>

                  <div className="space-y-2 border-t border-border/50 pt-3 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="flex items-center gap-1.5 text-muted-foreground">
                        <Clock className="w-4 h-4" /> SLA window
                      </span>
                      <span className="font-medium tabular-nums">{sla}h</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Outreach</span>
                      {comms === 'varies' ? (
                        <Badge variant="secondary">Varies</Badge>
                      ) : comms ? (
                        <Badge variant="warning">Sends a message</Badge>
                      ) : (
                        <Badge variant="secondary">None</Badge>
                      )}
                    </div>
                    {runId && (
                      <div className="flex items-center justify-between">
                        <span className="text-muted-foreground">In this run</span>
                        <span className="font-medium tabular-nums">
                          {count} invoice{count === 1 ? '' : 's'}
                        </span>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          );
        })}
      </div>

      <p className="text-xs text-muted-foreground">
        Rule changes apply to the <span className="font-medium">next run</span> — existing runs keep
        the routing they were processed with (for an auditable trail). To preview the impact on the
        current run before saving, use <span className="font-medium">Settings → Rules → Simulate</span>.
      </p>
    </div>
  );
}
