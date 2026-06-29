import { motion } from 'framer-motion';
import { CheckCircle2, Circle, Loader2 } from 'lucide-react';
import type { ActivityLog } from '@/types';

interface ActivityTimelineProps {
  activities: ActivityLog[];
}

export function ActivityTimeline({ activities }: ActivityTimelineProps) {
  return (
    <div className="space-y-4">
      {activities.map((activity, index) => {
        const isCompleted = activity.status === 'completed';
        const isInProgress = activity.status === 'in-progress';

        return (
          <motion.div
            key={activity.id}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: index * 0.1 }}
            className="flex gap-4"
          >
            <div className="flex flex-col items-center">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center ${
                  isCompleted
                    ? 'bg-settled/12 border-2 border-settled'
                    : isInProgress
                    ? 'bg-pending/12 border-2 border-pending'
                    : 'bg-muted border-2 border-muted-foreground/30'
                }`}
              >
                {isCompleted ? (
                  <CheckCircle2 className="w-4 h-4 text-settled" />
                ) : isInProgress ? (
                  <Loader2 className="w-4 h-4 text-pending animate-spin" />
                ) : (
                  <Circle className="w-4 h-4 text-muted-foreground" />
                )}
              </div>
              {index < activities.length - 1 && (
                <div className="w-0.5 h-12 bg-border" />
              )}
            </div>

            <div className="flex-1 pb-6">
              <div className="flex items-start justify-between">
                <div>
                  <h4 className="font-semibold text-sm">{activity.action}</h4>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {activity.description}
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    By {activity.user}
                  </p>
                </div>
                <span className="text-xs text-muted-foreground">
                  {new Date(activity.timestamp).toLocaleTimeString()}
                </span>
              </div>
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}
