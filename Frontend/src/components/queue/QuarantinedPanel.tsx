import { useState } from 'react';
import { AlertTriangle, ChevronDown, ChevronRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useRun } from '@/hooks/useRun';

/**
 * Surfaces rows that failed ingestion validation (returned by the backend as
 * `quarantined[]`). Renders nothing when there are none.
 */
export function QuarantinedPanel() {
  const { quarantined } = useRun();
  const [open, setOpen] = useState(false);

  if (quarantined.length === 0) return null;

  return (
    <Card className="border-pending/30 bg-pending/5">
      <CardHeader className="cursor-pointer" onClick={() => setOpen((o) => !o)}>
        <CardTitle className="flex items-center gap-2 text-base">
          {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          <AlertTriangle className="w-5 h-5 text-pending" />
          {quarantined.length} row{quarantined.length === 1 ? '' : 's'} quarantined at ingestion
          <Badge variant="warning" className="ml-1">excluded from the queue</Badge>
        </CardTitle>
      </CardHeader>
      {open && (
        <CardContent>
          <div className="rounded-lg border overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground uppercase">Row</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground uppercase">Reason</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-muted-foreground uppercase">Raw data</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {quarantined.map((q) => (
                  <tr key={q.row_index} className="align-top">
                    <td className="px-3 py-2 font-mono text-xs">#{q.row_index}</td>
                    <td className="px-3 py-2">
                      <Badge variant="danger" className="mb-1">{q.reason_code}</Badge>
                      <p className="text-xs text-muted-foreground">{q.reason}</p>
                    </td>
                    <td className="px-3 py-2">
                      <code className="text-[11px] text-muted-foreground break-all">
                        {JSON.stringify(q.raw)}
                      </code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      )}
    </Card>
  );
}
