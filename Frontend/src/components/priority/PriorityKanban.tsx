import { motion } from 'framer-motion';
import { AlertCircle, MinusCircle, CheckCircle2 } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { formatCompactCurrency, formatCurrencyFull } from '@/lib/format';
import type { Exception, Priority } from '@/types';

interface PriorityKanbanProps {
  exceptions: Exception[];
}

// Priority columns use the exception ink scale, not a rainbow:
// overdue (red) → pending (ochre) → settled (verdigris).
const priorityConfig = {
  HIGH: {
    icon: AlertCircle,
    label: 'HIGH Priority',
    iconChip: 'bg-overdue/15 text-overdue',
    header: 'bg-overdue/[0.06] border-overdue/20',
    accent: 'bg-overdue',
    badge: 'danger',
  },
  MEDIUM: {
    icon: MinusCircle,
    label: 'MEDIUM Priority',
    iconChip: 'bg-pending/15 text-pending',
    header: 'bg-pending/[0.06] border-pending/20',
    accent: 'bg-pending',
    badge: 'warning',
  },
  LOW: {
    icon: CheckCircle2,
    label: 'LOW Priority',
    iconChip: 'bg-settled/15 text-settled',
    header: 'bg-settled/[0.06] border-settled/20',
    accent: 'bg-settled',
    badge: 'success',
  },
} as const;

export function PriorityKanban({ exceptions }: PriorityKanbanProps) {
  const TOP_N = 5;
  const groupedExceptions = {
    HIGH: exceptions.filter((e) => e.priority === 'HIGH'),
    MEDIUM: exceptions.filter((e) => e.priority === 'MEDIUM'),
    LOW: exceptions.filter((e) => e.priority === 'LOW'),
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {(Object.keys(groupedExceptions) as Priority[]).map((priority) => {
        const config = priorityConfig[priority];
        const Icon = config.icon;
        const all = groupedExceptions[priority];
        const items = all.slice(0, TOP_N);

        return (
          <motion.div
            key={priority}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-4"
          >
            <div
              className={`flex items-center gap-2 p-3 rounded-md border ${config.header}`}
            >
              <div
                className={`w-8 h-8 rounded-md flex items-center justify-center ${config.iconChip}`}
              >
                <Icon className="w-4 h-4" />
              </div>
              <div>
                <h3 className="font-semibold text-sm">{config.label}</h3>
                <p className="font-mono text-xs text-muted-foreground tabular-nums">
                  {all.length} exception{all.length === 1 ? '' : 's'}
                  {all.length > TOP_N ? ` · top ${TOP_N}` : ''}
                </p>
              </div>
            </div>

            <div className="space-y-3">
              {items.map((exception, index) => (
                <motion.div
                  key={exception.id}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.05 }}
                >
                  <Card
                    className={`relative cursor-pointer overflow-hidden transition-all duration-200 ${
                      priority === 'HIGH' ? 'border-overdue/30 hover:border-overdue/50' : ''
                    }`}
                  >
                    {/* Ledger-margin accent in the column's severity ink. */}
                    <span className={`absolute inset-y-0 left-0 w-[3px] ${config.accent}`} aria-hidden />
                    <CardContent className="p-4 space-y-3">
                      <div className="flex items-start justify-between">
                        <div>
                          <p className="font-mono text-xs text-muted-foreground">
                            {exception.invoiceId}
                          </p>
                          <p className="text-sm font-semibold mt-1">
                            {exception.vendorName}
                          </p>
                        </div>
                        <Badge variant={config.badge}>
                          {exception.severity}
                        </Badge>
                      </div>

                      <div className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground">Amount</span>
                        <span className="font-semibold" title={formatCurrencyFull(exception.invoiceAmount)}>
                          {formatCompactCurrency(exception.invoiceAmount)}
                        </span>
                      </div>

                      <div className="pt-2 border-t border-border/50">
                        <p className="text-xs text-muted-foreground mb-1">
                          {exception.exceptionType}
                        </p>
                        <Badge variant="secondary" className="text-xs">
                          Action: Review
                        </Badge>
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>
              ))}
              {all.length > items.length && (
                <p className="pt-1 text-center text-xs text-muted-foreground">
                  +{all.length - items.length} more — see the Exception Queue
                </p>
              )}
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}
