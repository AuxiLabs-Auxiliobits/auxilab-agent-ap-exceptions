import { motion } from 'framer-motion';
import { CheckCircle2, Clock, Users, Zap, GitBranch } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import type { ResolutionPath, ResolutionType } from '@/types';

interface ResolutionPathCardsProps {
  paths: ResolutionPath[];
}

const iconMap: Record<ResolutionType, React.ElementType> = {
  'Auto Approve': CheckCircle2,
  'Escalate to Finance Controller': Users,
  'Request Missing PO': GitBranch,
  'Hold for Investigation': Clock,
  'Vendor Clarification Required': Zap,
};

// Each path maps to a semantic tone on the exception scale (settled / pending /
// overdue) rather than a rainbow — grouped by urgency.
type Tone = 'settled' | 'pending' | 'overdue';

const toneMap: Record<ResolutionType, Tone> = {
  'Auto Approve': 'settled',
  'Escalate to Finance Controller': 'overdue',
  'Request Missing PO': 'pending',
  'Hold for Investigation': 'overdue',
  'Vendor Clarification Required': 'pending',
};

const chipClass: Record<Tone, string> = {
  settled: 'bg-settled/12 text-settled',
  pending: 'bg-pending/12 text-pending',
  overdue: 'bg-overdue/12 text-overdue',
};
const borderClass: Record<Tone, string> = {
  settled: 'border-settled/20',
  pending: 'border-pending/20',
  overdue: 'border-overdue/20',
};

export function ResolutionPathCards({ paths }: ResolutionPathCardsProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {paths.map((path, index) => {
        const Icon = iconMap[path.type];
        const tone = toneMap[path.type];

        return (
          <motion.div
            key={path.id}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.1 }}
          >
            <Card className={`h-full ${borderClass[tone]}`}>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-3">
                  <div
                    className={`w-12 h-12 rounded-xl flex items-center justify-center ${chipClass[tone]}`}
                  >
                    <Icon className="w-6 h-6" />
                  </div>
                  <span className="text-base leading-tight">{path.type}</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-sm text-muted-foreground">
                  {path.description}
                </p>

                <div className="space-y-3 pt-2 border-t border-border/50">
                  <div className="flex items-start gap-2">
                    <GitBranch className="w-4 h-4 text-muted-foreground mt-0.5 shrink-0" />
                    <div>
                      <p className="text-xs text-muted-foreground">Logic</p>
                      <p className="text-sm font-mono">{path.logic}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <Users className="w-4 h-4 text-muted-foreground shrink-0" />
                    <div>
                      <p className="text-xs text-muted-foreground">
                        Assigned Team
                      </p>
                      <p className="text-sm">{path.assignedTeam}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <Clock className="w-4 h-4 text-muted-foreground shrink-0" />
                    <div>
                      <p className="text-xs text-muted-foreground">SLA Time</p>
                      <p className="text-sm font-medium">{path.slaTime}</p>
                    </div>
                  </div>
                </div>

                <div className="pt-3 border-t border-border/50">
                  <Badge
                    variant={
                      path.automationStatus === 'Automated'
                        ? 'success'
                        : path.automationStatus === 'Semi-Automated'
                        ? 'warning'
                        : 'secondary'
                    }
                    className="w-full justify-center"
                  >
                    {path.automationStatus}
                  </Badge>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        );
      })}
    </div>
  );
}
