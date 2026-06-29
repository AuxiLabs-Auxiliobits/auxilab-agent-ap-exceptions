import { AnalyticsCharts } from '@/components/analytics/AnalyticsCharts';
import { TrendsSection } from '@/components/analytics/TrendsSection';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { motion } from 'framer-motion';
import { Gauge, Target, TrendingUp, ShieldAlert } from 'lucide-react';
import { useRun } from '@/hooks/useRun';

function AnalyticsSkeleton() {
  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i} className="overflow-hidden">
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div className="space-y-2">
                  <Skeleton className="h-3 w-24" />
                  <Skeleton className="h-7 w-16" />
                </div>
                <Skeleton className="h-10 w-10 rounded-lg" />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i}>
            <CardContent className="p-6">
              <Skeleton className="h-4 w-40 mb-4" />
              <Skeleton className="h-56 w-full" />
            </CardContent>
          </Card>
        ))}
      </div>
    </>
  );
}

export function AnalyticsPage() {
  const { analyticsData, dashboardStats, metrics, isLoadingData } = useRun();

  // Analytics shows *rates* (Dashboard already shows the absolute counts), so
  // the two screens never duplicate each other.
  const total = metrics?.total_exceptions ?? 0;
  const pct = (n: number) => (total ? `${Math.round((n / total) * 100)}%` : '—');

  const kpis = [
    {
      label: 'Auto-Resolution Rate',
      value: dashboardStats ? `${dashboardStats.resolutionRate}%` : '—',
      hint: 'Cleared without a human',
      icon: Target,
      chip: 'bg-settled/12 text-settled',
    },
    {
      label: 'Escalation Rate',
      value: metrics ? pct(metrics.escalations_required) : '—',
      hint: 'Routed to a controller',
      icon: TrendingUp,
      chip: 'bg-pending/12 text-pending',
    },
    {
      label: 'Avg Confidence',
      value: metrics ? `${Math.round(metrics.average_confidence * 100)}%` : '—',
      hint: 'Model classification confidence',
      icon: Gauge,
      chip: 'bg-primary/12 text-primary',
    },
    {
      label: 'SLA At Risk',
      value: metrics ? pct(metrics.sla_at_risk_count) : '—',
      hint: 'Approaching or past deadline',
      icon: ShieldAlert,
      chip: 'bg-overdue/12 text-overdue',
    },
  ];

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-display text-3xl font-semibold tracking-tight">Analytics</h1>
        <p className="text-muted-foreground mt-1">
          Insights and metrics for AP exception processing
        </p>
      </div>

      {/* Cross-run trends — independent of the active run. */}
      <section className="space-y-3">
        <h2 className="font-display text-xl font-semibold tracking-tight">Trends across runs</h2>
        <TrendsSection />
      </section>

      {/* The active run's breakdown. */}
      <section className="space-y-3">
        <h2 className="font-display text-xl font-semibold tracking-tight">This run</h2>
        {isLoadingData && !analyticsData ? (
          <AnalyticsSkeleton />
        ) : analyticsData ? (
          <>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              {kpis.map((kpi, index) => (
                <motion.div
                  key={kpi.label}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.1 }}
                >
                  <Card className="h-full overflow-hidden transition-shadow hover:shadow-md">
                    <CardContent className="p-5">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                            {kpi.label}
                          </p>
                          <p className="mt-2 text-3xl font-bold tabular-nums">{kpi.value}</p>
                          <p className="mt-1 text-xs text-muted-foreground">{kpi.hint}</p>
                        </div>
                        <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${kpi.chip}`}>
                          <kpi.icon className="h-5 w-5" />
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>
              ))}
            </div>

            <AnalyticsCharts data={analyticsData} />
          </>
        ) : (
          <Card>
            <CardContent className="pt-6 text-sm text-muted-foreground">
              Upload or select a run to see its full breakdown.
            </CardContent>
          </Card>
        )}
      </section>
    </div>
  );
}
