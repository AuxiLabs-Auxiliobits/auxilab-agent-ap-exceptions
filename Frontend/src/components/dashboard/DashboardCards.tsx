import { motion } from 'framer-motion';
import {
  CheckCircle2,
  AlertTriangle,
  Flame,
  Gauge,
  type LucideIcon,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { formatCompactNumber } from '@/lib/format';
import type { DashboardStats } from '@/types';

interface DashboardCardsProps {
  stats: DashboardStats;
  /** Render placeholder tiles while the run's metrics are still loading. */
  loading?: boolean;
}

/**
 * Operational ledger tiles — throughput metrics that sit *beneath* the
 * Reconciliation Strip (which owns the money lifecycle). No fabricated trend
 * deltas: every figure is read straight from the run's metrics.
 */
interface Tile {
  title: string;
  icon: LucideIcon;
  accent: string; // text color for icon + value
  swatch: string; // bg for the icon chip
  value: (s: DashboardStats) => string;
  hint: string;
}

const tiles: Tile[] = [
  {
    title: 'Auto-resolvable',
    icon: CheckCircle2,
    accent: 'text-settled',
    swatch: 'bg-settled/12 ring-settled/30',
    value: (s) => formatCompactNumber(s.autoResolvable),
    hint: 'clear without a human',
  },
  {
    title: 'Escalations required',
    icon: AlertTriangle,
    accent: 'text-pending',
    swatch: 'bg-pending/12 ring-pending/30',
    value: (s) => formatCompactNumber(s.escalationsRequired),
    hint: 'routed to a controller',
  },
  {
    title: 'High severity',
    icon: Flame,
    accent: 'text-overdue',
    swatch: 'bg-overdue/12 ring-overdue/30',
    value: (s) => formatCompactNumber(s.highSeverityCount),
    hint: 'in the red — act first',
  },
  {
    title: 'Resolution rate',
    icon: Gauge,
    accent: 'text-primary',
    swatch: 'bg-primary/12 ring-primary/30',
    // resolutionRate may arrive as 0–1 or 0–100; normalise to a percentage.
    value: (s) => `${Math.round(s.resolutionRate <= 1 ? s.resolutionRate * 100 : s.resolutionRate)}%`,
    hint: 'auto-cleared share',
  },
];

export function DashboardCards({ stats, loading = false }: DashboardCardsProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {tiles.map((tile) => (
          <Card key={tile.title} className="h-full">
            <CardContent className="p-5">
              <div className="flex items-center justify-between">
                <Skeleton className="h-3 w-24" />
                <Skeleton className="h-7 w-7 rounded-md" />
              </div>
              <Skeleton className="mt-3 h-9 w-20" />
              <Skeleton className="mt-2 h-3 w-28" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {tiles.map((tile, index) => {
        const Icon = tile.icon;
        return (
          <motion.div
            key={tile.title}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.06, duration: 0.3 }}
          >
            <Card className="group relative h-full overflow-hidden transition-colors hover:border-primary/40">
              {/* Verdigris hover sheen */}
              <div
                className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100 bg-gradient-to-br from-primary/[0.07] via-transparent to-transparent"
                aria-hidden
              />
              <CardContent className="relative p-5">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    {tile.title}
                  </p>
                  <span className={`grid h-7 w-7 place-items-center rounded-md ring-1 ${tile.swatch}`}>
                    <Icon className={`h-4 w-4 ${tile.accent}`} aria-hidden />
                  </span>
                </div>
                <p className={`mt-3 font-mono text-3xl font-medium tabular-nums ${tile.accent}`}>
                  {tile.value(stats)}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">{tile.hint}</p>
              </CardContent>
            </Card>
          </motion.div>
        );
      })}
    </div>
  );
}
