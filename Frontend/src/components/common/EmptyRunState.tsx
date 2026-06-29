import { Link } from 'react-router-dom';
import { Inbox, AlertCircle } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useRun } from '@/hooks/useRun';

/**
 * Shared placeholder for data pages when there is no run yet, the run is
 * still processing, the data is loading, or the backend errored. Returns
 * `null` once results exist so the page can render its real content.
 *
 * While waiting for content (uploading / processing / loading) it shows a
 * content-shaped skeleton — stat tiles + a list — rather than a spinner, so the
 * layout doesn't jump when data arrives. The optional caption keeps the live
 * status (e.g. the agent's current step) visible above the skeleton.
 */
function LoadingSkeleton({ caption }: { caption?: string }) {
  return (
    <div className="space-y-6" aria-busy="true">
      {caption && <p className="text-sm text-muted-foreground">{caption}</p>}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i}>
            <CardContent className="pt-6">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="mt-3 h-8 w-16" />
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardContent className="space-y-3 pt-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-11 w-full" />
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function StateCard({
  icon,
  title,
  message,
  action,
}: {
  icon: React.ReactNode;
  title: string;
  message: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <Card className="min-h-[360px] flex items-center justify-center">
      <CardContent className="flex flex-col items-center text-center pt-6">
        {icon}
        <h3 className="text-lg font-semibold mb-1">{title}</h3>
        <p className="text-sm text-muted-foreground max-w-md break-words">{message}</p>
        {action}
      </CardContent>
    </Card>
  );
}

export function EmptyRunState() {
  const { runId, isProcessing, isLoadingData, isUploading, currentNode, error } =
    useRun();

  if (error) {
    return (
      <StateCard
        icon={<AlertCircle className="w-12 h-12 text-overdue/70 mb-4" />}
        title="Something went wrong"
        message={error}
      />
    );
  }

  if (isUploading) {
    return <LoadingSkeleton caption="Uploading your file to the agent…" />;
  }
  if (isProcessing) {
    return (
      <LoadingSkeleton
        caption={
          currentNode
            ? `Agent is processing — current step: ${currentNode}`
            : 'Agent is processing — classifying, routing and drafting communications…'
        }
      />
    );
  }
  if (isLoadingData) {
    return <LoadingSkeleton caption="Loading results…" />;
  }

  return (
    <StateCard
      icon={<Inbox className="w-12 h-12 text-muted-foreground/50 mb-4" />}
      title="No run yet"
      message="Upload an exception queue on the Dashboard to populate this view."
      action={
        !runId ? (
          <Button asChild className="mt-4" variant="outline">
            <Link to="/dashboard">Go to Dashboard</Link>
          </Button>
        ) : undefined
      }
    />
  );
}
