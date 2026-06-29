import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  LabelList,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { motion } from 'framer-motion';
import { formatCompactCurrency, formatCurrencyFull } from '@/lib/format';
import type { AnalyticsData } from '@/types';
import {
  AXIS_TICK,
  BAR_CURSOR,
  CATEGORICAL,
  CHART_COLORS,
  SEVERITY_FILLS,
  TOOLTIP,
} from './chartTheme';

interface AnalyticsChartsProps {
  data: AnalyticsData;
}

const sumValues = (rows: { value: number }[]) => rows.reduce((acc, r) => acc + r.value, 0);

function ChartCard({
  title,
  subtitle,
  delay = 0,
  children,
}: {
  title: string;
  subtitle?: string;
  delay?: number;
  children: React.ReactNode;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.35 }}
      className="h-full"
    >
      <Card className="h-full">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-semibold">{title}</CardTitle>
          {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
        </CardHeader>
        <CardContent>{children}</CardContent>
      </Card>
    </motion.div>
  );
}

function EmptyChart({ height }: { height: number }) {
  return (
    <div
      className="flex items-center justify-center text-sm text-muted-foreground"
      style={{ height }}
    >
      No data for this run yet.
    </div>
  );
}

/** Donut with a center total and a clean two-column legend (replaces cramped,
 *  overlapping slice labels). */
function Donut({
  data,
  colors,
  unit,
  height = 230,
}: {
  data: { name: string; value: number }[];
  colors: string[];
  unit: string;
  height?: number;
}) {
  const total = sumValues(data);
  if (!total) return <EmptyChart height={height + 60} />;
  return (
    <div>
      <div className="relative" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              innerRadius={64}
              outerRadius={94}
              paddingAngle={data.length > 1 ? 3 : 0}
              stroke="none"
            >
              {data.map((_, i) => (
                <Cell key={i} fill={colors[i % colors.length]} />
              ))}
            </Pie>
            <Tooltip
              {...TOOLTIP}
              formatter={(value, name) => {
                const v = Number(value);
                return [`${v} (${Math.round((v / total) * 100)}%)`, name];
              }}
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-3xl font-bold tabular-nums">{total}</span>
          <span className="text-xs text-muted-foreground">{unit}</span>
        </div>
      </div>
      <ul className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
        {data.map((d, i) => (
          <li key={d.name} className="flex items-center justify-between gap-2">
            <span className="flex min-w-0 items-center gap-2">
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-sm"
                style={{ background: colors[i % colors.length] }}
              />
              <span className="truncate text-muted-foreground">{d.name}</span>
            </span>
            <span className="shrink-0 font-medium tabular-nums">
              {Math.round((d.value / total) * 100)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function AnalyticsCharts({ data }: AnalyticsChartsProps) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Exceptions by Type — horizontal bars + value labels */}
        <ChartCard
          title="Exceptions by Type"
          subtitle="Count of exceptions in each category"
          delay={0.05}
        >
          {data.exceptionsByType.length ? (
            <div className="h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={data.exceptionsByType}
                  layout="vertical"
                  margin={{ left: 8, right: 28 }}
                >
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} className="stroke-border/60" />
                  <XAxis type="number" tick={AXIS_TICK} axisLine={false} tickLine={false} allowDecimals={false} />
                  <YAxis
                    dataKey="name"
                    type="category"
                    width={120}
                    tick={AXIS_TICK}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip {...TOOLTIP} cursor={BAR_CURSOR} />
                  <Bar dataKey="value" fill={CHART_COLORS.blue} radius={[0, 6, 6, 0]} maxBarSize={26}>
                    <LabelList dataKey="value" position="right" className="fill-muted-foreground text-[11px]" />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyChart height={300} />
          )}
        </ChartCard>

        {/* Severity Distribution — donut */}
        <ChartCard
          title="Severity Distribution"
          subtitle="Share of exceptions by severity"
          delay={0.1}
        >
          <Donut data={data.severityDistribution} colors={SEVERITY_FILLS} unit="exceptions" />
        </ChartCard>
      </div>

      {/* Exception Value by Type — full-width vertical bars */}
      <ChartCard
        title="Exception Value by Type"
        subtitle="Dollar exposure across exception categories"
        delay={0.15}
      >
        {data.valueByType.length ? (
          <div className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.valueByType} margin={{ top: 8, right: 8 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} className="stroke-border/60" />
                <XAxis
                  dataKey="name"
                  tick={{ ...AXIS_TICK, fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  interval={0}
                  angle={-15}
                  textAnchor="end"
                  height={64}
                />
                <YAxis
                  tick={AXIS_TICK}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={formatCompactCurrency}
                  width={64}
                />
                <Tooltip
                  {...TOOLTIP}
                  cursor={BAR_CURSOR}
                  formatter={(value) => [formatCurrencyFull(Number(value)), 'Exposure']}
                />
                <Bar dataKey="value" fill={CHART_COLORS.blue} radius={[6, 6, 0, 0]} maxBarSize={56} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <EmptyChart height={300} />
        )}
      </ChartCard>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Resolution Status — donut */}
        <ChartCard
          title="Resolution Status"
          subtitle="How exceptions were routed"
          delay={0.2}
        >
          <Donut data={data.resolutionStatus} colors={CATEGORICAL} unit="exceptions" />
        </ChartCard>

        {/* Top Vendors — vertical bars + value labels */}
        <ChartCard
          title="Top Vendors by Exceptions"
          subtitle="Vendors with the most exceptions this run"
          delay={0.25}
        >
          {data.topVendors.length ? (
            <div className="h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.topVendors} margin={{ top: 16, right: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} className="stroke-border/60" />
                  <XAxis
                    dataKey="name"
                    tick={{ ...AXIS_TICK, fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                    interval={0}
                  />
                  <YAxis tick={AXIS_TICK} axisLine={false} tickLine={false} allowDecimals={false} width={32} />
                  <Tooltip {...TOOLTIP} cursor={BAR_CURSOR} />
                  <Bar dataKey="exceptions" fill={CHART_COLORS.blue} radius={[6, 6, 0, 0]} maxBarSize={52}>
                    <LabelList dataKey="exceptions" position="top" className="fill-muted-foreground text-[11px]" />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyChart height={300} />
          )}
        </ChartCard>
      </div>
    </div>
  );
}
