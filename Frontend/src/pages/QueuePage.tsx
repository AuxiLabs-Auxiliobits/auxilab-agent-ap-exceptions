import { useSearchParams } from 'react-router-dom';
import { LayoutList, KanbanSquare } from 'lucide-react';
import { ExceptionTable } from '@/components/queue/ExceptionTable';
import { PriorityKanban } from '@/components/priority/PriorityKanban';
import { QuarantinedPanel } from '@/components/queue/QuarantinedPanel';
import { EmptyRunState } from '@/components/common/EmptyRunState';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { useRun } from '@/hooks/useRun';

function QueueTableSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-9 w-full max-w-sm" />
      </CardHeader>
      <CardContent className="space-y-3">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </CardContent>
    </Card>
  );
}

type ViewKey = 'table' | 'priority';

/**
 * Exceptions — one screen, two lenses over the SAME exception list:
 *   • Table:    the full, searchable/filterable/sortable working queue.
 *   • Priority: the same items triaged into HIGH/MEDIUM/LOW by priority score.
 * The view is in the URL (?view=priority) so it's linkable and the old
 * /priority route can redirect straight to the board.
 */
export function QueuePage() {
  const { exceptions, isLoadingData } = useRun();
  const [params, setParams] = useSearchParams();
  const view: ViewKey = params.get('view') === 'priority' ? 'priority' : 'table';

  const setView = (next: ViewKey) => {
    const p = new URLSearchParams(params);
    if (next === 'table') p.delete('view');
    else p.set('view', next);
    setParams(p, { replace: true });
  };

  const tabs: { key: ViewKey; label: string; icon: typeof LayoutList }[] = [
    { key: 'table', label: 'Table', icon: LayoutList },
    { key: 'priority', label: 'Priority board', icon: KanbanSquare },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold tracking-tight">Exceptions</h1>
          <p className="text-muted-foreground mt-1">
            {view === 'priority'
              ? 'The same exceptions, triaged by priority — clear the HIGH column first.'
              : 'Search, filter, and process every accounts-payable exception in this run.'}
          </p>
        </div>

        {/* View toggle — Table vs Priority board, same underlying data. */}
        <div className="inline-flex rounded-lg border bg-card p-1" role="tablist" aria-label="Exceptions view">
          {tabs.map((t) => {
            const active = view === t.key;
            return (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setView(t.key)}
                className={cn(
                  'inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                  active
                    ? 'bg-primary/10 text-primary'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                <t.icon className="h-4 w-4" />
                {t.label}
              </button>
            );
          })}
        </div>
      </div>

      {view === 'table' && <QuarantinedPanel />}

      {isLoadingData && exceptions.length === 0 ? (
        <QueueTableSkeleton />
      ) : exceptions.length > 0 ? (
        view === 'priority' ? (
          <PriorityKanban exceptions={exceptions} />
        ) : (
          <ExceptionTable exceptions={exceptions} />
        )
      ) : (
        <EmptyRunState />
      )}
    </div>
  );
}
