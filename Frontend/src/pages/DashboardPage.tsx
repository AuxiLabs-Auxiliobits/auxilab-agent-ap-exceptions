import { motion } from 'framer-motion';
import { DashboardCards } from '@/components/dashboard/DashboardCards';
import { UploadPanel } from '@/components/dashboard/UploadPanel';
import { ActivityTimeline } from '@/components/dashboard/ActivityTimeline';
import { ReconciliationStrip } from '@/components/signature/ReconciliationStrip';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Activity, Inbox, Loader2 } from 'lucide-react';
import { useRun } from '@/hooks/useRun';
import type { DashboardStats } from '@/types';

const EMPTY_STATS: DashboardStats = {
  totalExceptions: 0,
  autoResolvable: 0,
  escalationsRequired: 0,
  totalExceptionValue: 0,
  highSeverityCount: 0,
  resolutionRate: 0,
  avgProcessingTime: 0,
};

export function DashboardPage() {
  const { dashboardStats, activities, runId, isProcessing, isLoadingData, exceptions, metrics } =
    useRun();

  return (
    <div className="space-y-6">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.5 }}
      >
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="font-display text-3xl font-semibold tracking-tight">
              Clearing desk
            </h1>
            <p className="text-muted-foreground mt-1">
              Your suspended balance, by what each dollar is waiting on.
            </p>
          </div>
          {isProcessing && (
            <span className="flex items-center gap-2 text-sm font-medium text-pending">
              <Loader2 className="h-4 w-4 animate-spin" />
              Agent is processing…
            </span>
          )}
        </div>

        {/* Signature element — the reconciliation ledger bar. */}
        <ReconciliationStrip
          exceptions={exceptions}
          averageConfidence={metrics?.average_confidence}
          className="mb-6"
        />

        <DashboardCards
          stats={dashboardStats ?? EMPTY_STATS}
          loading={isLoadingData && !dashboardStats}
        />

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-6">
          <div className="lg:col-span-1">
            <UploadPanel />
          </div>

          <div className="lg:col-span-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Activity className="w-5 h-5 text-primary" />
                  Processing trail
                </CardTitle>
              </CardHeader>
              <CardContent>
                {activities.length > 0 ? (
                  // Cap the visible trail to ~4 events, then scroll — long runs
                  // record many events and shouldn't push the page down endlessly.
                  <div className="max-h-[340px] overflow-y-auto pr-2">
                    <ActivityTimeline activities={activities} />
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center text-center py-12 text-muted-foreground">
                    <Inbox className="w-10 h-10 mb-3 opacity-50" />
                    <p className="text-sm">
                      {runId
                        ? 'Waiting for the agent to record activity…'
                        : 'Upload an exception queue to start a run.'}
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
