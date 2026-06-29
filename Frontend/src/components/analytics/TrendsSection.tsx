import { useEffect, useState } from 'react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { TrendingUp } from 'lucide-react';
import { api, ApiError, type TrendsResponse } from '@/lib/api';
import { formatCompactCurrency, formatCompactNumber } from '@/lib/format';
import { AXIS_TICK, BAR_CURSOR, CHART_COLORS, TOOLTIP } from './chartTheme';

const shortDate = (iso: string | null) => {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? '—'
    : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
};

const fmtHours = (h: number | null) => {
  if (h == null) return '—';
  if (h < 1) return `${Math.round(h * 60)}m`;
  if (h < 24) return `${h.toFixed(1)}h`;
  return `${(h / 24).toFixed(1)}d`;
};

export function TrendsSection() {
  const [data, setData] = useState<TrendsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .getTrends()
      .then((res) => {
        if (alive) setData(res);
      })
      .catch((e) => {
        if (alive) setError(e instanceof ApiError ? e.message : String(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  if (loading) return <TrendsSkeleton />;
  if (error) {
    return (
      <Card className="border-overdue/30">
        <CardContent className="pt-4 text-sm text-overdue break-words">{error}</CardContent>
      </Card>
    );
  }
  if (!data || data.totals.runs === 0) {
    return (
      <Card>
        <CardContent className="flex items-center gap-3 pt-6 text-muted-foreground">
          <TrendingUp className="h-5 w-5 shrink-0" />
          Trends appear here once you’ve processed a run or two.
        </CardContent>
      </Card>
    );
  }

  const t = data.totals;
  const series = data.runs.map((r) => ({
    name: shortDate(r.created_at),
    exceptions: r.total_exceptions,
    resolutionRate: r.total_exceptions ? Math.round((r.closed / r.total_exceptions) * 100) : 0,
    cycle: r.avg_cycle_hours,
    value: Number(r.total_value),
  }));

  return (
    <div className="space-y-4">
      {/* ---- Totals strip ---- */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat label="Runs processed" value={formatCompactNumber(t.runs)} />
        <Stat label="Exceptions handled" value={formatCompactNumber(t.total_exceptions)} hint={formatCompactCurrency(Number(t.total_value))} />
        <Stat label="Resolution rate" value={`${Math.round(t.resolution_rate * 100)}%`} hint={`${t.closed} closed`} />
        <Stat label="Avg time to resolve" value={fmtHours(t.avg_cycle_hours)} hint="run start → closed" />
      </div>

      {/* ---- Charts ---- */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartCard title="Exceptions per run" subtitle="Volume handled each run">
          <BarChart data={series} margin={{ top: 8 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} className="stroke-border/60" />
            <XAxis dataKey="name" tick={AXIS_TICK} axisLine={false} tickLine={false} />
            <YAxis tick={AXIS_TICK} axisLine={false} tickLine={false} allowDecimals={false} />
            <Tooltip {...TOOLTIP} cursor={BAR_CURSOR} />
            <Bar dataKey="exceptions" name="Exceptions" fill={CHART_COLORS.blue} radius={[4, 4, 0, 0]} maxBarSize={44} />
          </BarChart>
        </ChartCard>

        <ChartCard title="Resolution rate per run" subtitle="% of exceptions closed">
          <LineChart data={series} margin={{ top: 8 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} className="stroke-border/60" />
            <XAxis dataKey="name" tick={AXIS_TICK} axisLine={false} tickLine={false} />
            <YAxis tick={AXIS_TICK} axisLine={false} tickLine={false} domain={[0, 100]} unit="%" />
            <Tooltip {...TOOLTIP} />
            <Line
              type="monotone"
              dataKey="resolutionRate"
              name="Resolved %"
              stroke={CHART_COLORS.green}
              strokeWidth={2.5}
              dot={{ r: 3, strokeWidth: 0, fill: CHART_COLORS.green }}
              activeDot={{ r: 5 }}
            />
          </LineChart>
        </ChartCard>

        <ChartCard title="Avg time to resolve" subtitle="Hours from run start to closed">
          <LineChart data={series} margin={{ top: 8 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} className="stroke-border/60" />
            <XAxis dataKey="name" tick={AXIS_TICK} axisLine={false} tickLine={false} />
            <YAxis tick={AXIS_TICK} axisLine={false} tickLine={false} />
            <Tooltip {...TOOLTIP} />
            <Line
              type="monotone"
              dataKey="cycle"
              name="Hours"
              stroke={CHART_COLORS.blue}
              strokeWidth={2.5}
              dot={{ r: 3, strokeWidth: 0, fill: CHART_COLORS.blue }}
              activeDot={{ r: 5 }}
              connectNulls
            />
          </LineChart>
        </ChartCard>

        <ChartCard title="Exception value per run" subtitle="Total dollar exposure each run">
          <BarChart data={series} margin={{ top: 8 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} className="stroke-border/60" />
            <XAxis dataKey="name" tick={AXIS_TICK} axisLine={false} tickLine={false} />
            <YAxis tick={AXIS_TICK} axisLine={false} tickLine={false} tickFormatter={(v) => formatCompactCurrency(Number(v))} width={70} />
            <Tooltip {...TOOLTIP} cursor={BAR_CURSOR} formatter={(v) => [formatCompactCurrency(Number(v)), 'Value']} />
            <Bar dataKey="value" name="Value" fill={CHART_COLORS.blue} radius={[4, 4, 0, 0]} maxBarSize={44} />
          </BarChart>
        </ChartCard>
      </div>
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card className="overflow-hidden">
      <CardContent className="p-4">
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
        <p className="mt-2 font-mono text-2xl font-medium tabular-nums">{value}</p>
        {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  );
}

function ChartCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactElement;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{title}</CardTitle>
        {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
      </CardHeader>
      <CardContent>
        <div className="h-[240px]">
          <ResponsiveContainer width="100%" height="100%">
            {children}
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

function TrendsSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i}>
            <CardContent className="p-4">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="mt-3 h-7 w-16" />
            </CardContent>
          </Card>
        ))}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {Array.from({ length: 2 }).map((_, i) => (
          <Card key={i}>
            <CardContent className="p-5">
              <Skeleton className="h-4 w-40 mb-4" />
              <Skeleton className="h-[200px] w-full" />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
