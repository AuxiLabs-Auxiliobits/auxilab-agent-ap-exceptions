import { Bell, History, CheckCircle2, Loader2, AlertTriangle, AlarmClock } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ThemeToggle } from './ThemeToggle';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Badge } from '@/components/ui/badge';
import { useNavigate } from 'react-router-dom';
import { UserButton } from '@clerk/react';
import { useRun } from '@/hooks/useRun';
import { useSla } from '@/hooks/useSla';
import { usePermissions } from '@/hooks/usePermissions';

function shortId(runId: string): string {
  return runId.replace(/^run_/, '').slice(0, 8);
}

function shortDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function Header() {
  const navigate = useNavigate();
  const { runId, history, status, selectRun, metrics, rowsQuarantined, isProcessing } = useRun();
  const { atRisk, breached, dueSoon } = useSla();
  const { role } = usePermissions();

  const escalations = metrics?.escalations_required ?? 0;
  // The badge counts genuinely urgent items: escalations, quarantines, and SLA breaches.
  const notifCount = escalations + rowsQuarantined + breached;
  const hasAny = isProcessing || escalations > 0 || rowsQuarantined > 0 || atRisk > 0;

  return (
    <header className="h-16 border-b bg-card/50 backdrop-blur-sm sticky top-0 z-40">
      <div className="flex items-center justify-end h-full px-6 gap-4">
        <div className="flex items-center gap-3">
          {/* ---- Run history switcher ---- */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="gap-2 hidden sm:flex">
                <History className="h-4 w-4" />
                {runId ? (
                  <span className="font-mono text-xs">{shortId(runId)}</span>
                ) : (
                  <span className="text-xs text-muted-foreground">No run</span>
                )}
                {status && (
                  <Badge variant={status === 'FAILED' ? 'danger' : 'secondary'} className="text-[10px]">
                    {status}
                  </Badge>
                )}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-80 max-h-[70vh] overflow-auto">
              <DropdownMenuLabel>Run history</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {history.length === 0 && (
                <DropdownMenuItem disabled>No runs yet — upload a queue</DropdownMenuItem>
              )}
              {history.map((r) => (
                <DropdownMenuItem
                  key={r.runId}
                  onClick={() => selectRun(r.runId)}
                  className="flex items-start justify-between gap-2"
                >
                  <span className="flex items-start gap-2 min-w-0">
                    {r.runId === runId ? (
                      <CheckCircle2 className="h-3.5 w-3.5 text-primary mt-0.5 shrink-0" />
                    ) : (
                      <span className="w-3.5 shrink-0" />
                    )}
                    <span className="flex flex-col min-w-0">
                      <span className="text-xs font-medium truncate">
                        {r.fileName ?? shortId(r.runId)}
                      </span>
                      <span className="text-[10px] text-muted-foreground">
                        {shortDate(r.createdAt)} · {r.rowsAccepted} rows
                      </span>
                    </span>
                  </span>
                  <Badge
                    variant={r.status === 'FAILED' ? 'danger' : 'secondary'}
                    className="text-[10px] shrink-0"
                  >
                    {r.status}
                  </Badge>
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>

          {/* ---- Notifications ---- */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="relative">
                <Bell className="h-5 w-5" />
                {notifCount > 0 && (
                  <Badge
                    variant="danger"
                    className="absolute -top-1 -right-1 h-5 min-w-5 flex items-center justify-center p-0 text-xs"
                  >
                    {notifCount}
                  </Badge>
                )}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-72">
              <DropdownMenuLabel>Notifications</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {isProcessing && (
                <DropdownMenuItem disabled className="gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" /> Agent is processing…
                </DropdownMenuItem>
              )}
              {escalations > 0 && (
                <DropdownMenuItem onClick={() => navigate('/communications')} className="gap-2">
                  <AlertTriangle className="h-4 w-4 text-pending" />
                  {escalations} escalation{escalations === 1 ? '' : 's'} need review
                </DropdownMenuItem>
              )}
              {rowsQuarantined > 0 && (
                <DropdownMenuItem onClick={() => navigate('/queue')} className="gap-2">
                  <AlertTriangle className="h-4 w-4 text-overdue" />
                  {rowsQuarantined} row{rowsQuarantined === 1 ? '' : 's'} quarantined
                </DropdownMenuItem>
              )}
              {atRisk > 0 && (
                <DropdownMenuItem onClick={() => navigate('/sla')} className="gap-2">
                  <AlarmClock className={`h-4 w-4 ${breached > 0 ? 'text-overdue' : 'text-pending'}`} />
                  {breached > 0
                    ? `${breached} SLA breach${breached === 1 ? '' : 'es'}${dueSoon > 0 ? ` · ${dueSoon} due soon` : ''}`
                    : `${dueSoon} due soon`}
                </DropdownMenuItem>
              )}
              {!hasAny && (
                <DropdownMenuItem disabled>No new notifications</DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>

          <ThemeToggle />

          <div className="w-px h-6 bg-border" />

          {/* ---- Current RBAC role (from GET /v1/me) ---- */}
          {role && (
            <Badge
              variant="outline"
              className="hidden sm:inline-flex capitalize"
              title={`Your role: ${role}. It governs which actions you can take.`}
            >
              {role}
            </Badge>
          )}

          {/* ---- Clerk user menu (sign-out target is set on ClerkProvider) ---- */}
          <UserButton />
        </div>
      </div>
    </header>
  );
}
