import { useState } from 'react';
import { GitBranch, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { api, ApiError, type ResolutionPathEnum } from '@/lib/api';
import { RESOLUTION_PATH_LABELS } from '@/lib/resolutionLabels';

const PATHS: { value: ResolutionPathEnum; label: string }[] = (
  Object.entries(RESOLUTION_PATH_LABELS) as [ResolutionPathEnum, string][]
).map(([value, label]) => ({ value, label }));

/**
 * Compact per-invoice control to override the agent's resolution path. The
 * override is recorded (with the required reason) and feeds the most-overridden
 * rules report so admins can tune the org rulebook from real corrections.
 */
export function RerouteControl({
  runId,
  invoiceId,
  currentPath,
  disabled,
  onDone,
}: {
  runId: string | null;
  invoiceId?: string;
  currentPath?: ResolutionPathEnum;
  disabled?: boolean;
  onDone?: (msg: { kind: 'ok' | 'err'; text: string }) => void;
}) {
  const [open, setOpen] = useState(false);
  const [path, setPath] = useState<ResolutionPathEnum | ''>('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);

  if (!invoiceId) return null;

  const submit = async () => {
    if (!runId || !path || !reason.trim()) return;
    setBusy(true);
    try {
      await api.overrideResolution(runId, invoiceId, path, reason.trim());
      onDone?.({ kind: 'ok', text: `Re-routed ${invoiceId} → ${path}.` });
      setOpen(false);
      setReason('');
      setPath('');
    } catch (e) {
      onDone?.({ kind: 'err', text: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <Button
        variant="outline"
        size="sm"
        disabled={disabled}
        onClick={() => setOpen(true)}
        title={disabled ? 'Your role cannot change routing' : 'Override the resolution path for this invoice'}
        className="gap-2"
      >
        <GitBranch className="w-4 h-4" />
        Reroute
      </Button>
    );
  }

  return (
    <div className="w-full rounded-lg border bg-muted/30 p-3 space-y-2">
      <p className="text-xs text-muted-foreground">
        Override routing for <span className="font-mono">{invoiceId}</span>
        {currentPath && (
          <>
            {' '}— currently <span className="font-medium">{currentPath}</span>
          </>
        )}
        . Recorded for rulebook tuning.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Select value={path} onValueChange={(v) => setPath(v as ResolutionPathEnum)}>
          <SelectTrigger className="h-8 w-56 text-xs">
            <SelectValue placeholder="New path" />
          </SelectTrigger>
          <SelectContent>
            {PATHS.filter((p) => p.value !== currentPath).map((p) => (
              <SelectItem key={p.value} value={p.value}>
                {p.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Reason (required)"
          className="h-8 flex-1 min-w-[10rem] text-xs"
        />
        <Button size="sm" disabled={busy || !path || !reason.trim()} onClick={submit} className="gap-2">
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
          Apply
        </Button>
        <Button size="sm" variant="outline" disabled={busy} onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
