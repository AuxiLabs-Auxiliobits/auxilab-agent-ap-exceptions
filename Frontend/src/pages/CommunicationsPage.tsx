import { CommunicationTabs } from '@/components/communication/CommunicationTabs';
import { EmptyRunState } from '@/components/common/EmptyRunState';
import { useRun } from '@/hooks/useRun';

export function CommunicationsPage() {
  const { communications } = useRun();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold tracking-tight">Communications</h1>
        <p className="text-muted-foreground mt-1">
          AI-generated communication templates for exception resolution
        </p>
      </div>

      {communications.length > 0 ? (
        <CommunicationTabs communications={communications} />
      ) : (
        <EmptyRunState />
      )}
    </div>
  );
}
