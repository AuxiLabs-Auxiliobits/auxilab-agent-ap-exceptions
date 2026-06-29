import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Mail,
  MessageSquare,
  FileText,
  Copy,
  Edit,
  Eye,
  Send,
  Check,
  Loader2,
  CheckCircle2,
  AlertCircle,
  ShieldCheck,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  api,
  ApiError,
  type CommsPreview,
  type ResolutionDecision,
  type ResolutionPathEnum,
} from '@/lib/api';
import { useRun } from '@/hooks/useRun';
import { usePermissions } from '@/hooks/usePermissions';
import { CommsPreviewDialog } from './CommsPreviewDialog';
import { RerouteControl } from './RerouteControl';
import type { Communication, CommSendStatus } from '@/types';

interface CommunicationTabsProps {
  communications: Communication[];
}

const TYPE_ORDER: Communication['type'][] = [
  'Vendor Email',
  'Internal Slack',
  'Escalation Note',
];

// Bulk "Send all" is chunked into batches of this many invoices per request, so
// a run with hundreds of drafts never exceeds the request timeout. Sends are
// idempotent on the backend, so an interrupted bulk send resumes on re-click.
const SEND_ALL_BATCH_SIZE = 25;

const iconMap: Record<Communication['type'], React.ElementType> = {
  'Vendor Email': Mail,
  'Internal Slack': MessageSquare,
  'Escalation Note': FileText,
};

/**
 * A message counts as "handled" once it has been sent (live) or written in
 * dry-run mode. Drafts that are still unsent — including failed/skipped ones
 * that still need attention — are the "remaining" work the counters track.
 */
function isHandled(c: Communication): boolean {
  return c.sendStatus === 'sent' || c.sendStatus === 'dryrun';
}

// Resolution paths that never require an outbound message (requires_communication
// is always false for these in the rules policy). A draft sitting on one of these
// — e.g. after a reroute — no longer applies and must not be sent.
const NO_OUTREACH_PATHS = new Set<ResolutionPathEnum>(['AUTO_APPROVE', 'HOLD_INVESTIGATION']);

type DraftGuard =
  | { kind: 'superseded'; path: ResolutionPathEnum }
  | { kind: 'rerouted'; path: ResolutionPathEnum }
  | { kind: 'ok' };

/**
 * Decide whether a draft is still valid given the invoice's *current* resolution.
 * Uses only reliable signals so it can't drift from the backend:
 *  - superseded: the path now needs no outreach at all → block sending.
 *  - rerouted:   still a comms path, but a human changed the decision after the
 *                draft was written (the backend stamps `human_override` onto
 *                rule_id) → the message may no longer match, so warn before send.
 */
function draftGuard(res?: ResolutionDecision): DraftGuard {
  if (!res) return { kind: 'ok' };
  if (NO_OUTREACH_PATHS.has(res.resolution_path)) {
    return { kind: 'superseded', path: res.resolution_path };
  }
  if (res.rule_id?.includes('human_override')) {
    return { kind: 'rerouted', path: res.resolution_path };
  }
  return { kind: 'ok' };
}

function StatusBadge({ status }: { status?: CommSendStatus }) {
  switch (status) {
    case 'sent':
      return <Badge variant="success" className="gap-1"><CheckCircle2 className="w-3 h-3" />Sent</Badge>;
    case 'dryrun':
      return <Badge variant="warning" className="gap-1"><ShieldCheck className="w-3 h-3" />Dry-run</Badge>;
    case 'failed':
      return <Badge variant="danger" className="gap-1"><AlertCircle className="w-3 h-3" />Failed</Badge>;
    case 'skipped':
      return <Badge variant="secondary">Skipped</Badge>;
    default:
      return <Badge variant="secondary">Draft</Badge>;
  }
}

export function CommunicationTabs({ communications }: CommunicationTabsProps) {
  const { runId, reloadData, status, approve, results } = useRun();
  const { can } = usePermissions();
  const canSend = can('comms:send');
  const canEdit = can('draft:edit');
  const canApprove = can('run:approve');

  // Whether Slack is connected — drives the per-draft "→ Slack vs → Email"
  // target badge, so a reviewer sees where an escalation/Slack note will go.
  const [slackConnected, setSlackConnected] = useState(false);
  useEffect(() => {
    api
      .getConfig()
      .then((c) => setSlackConnected(!!c.comms?.slack_configured))
      .catch(() => {});
  }, []);

  // Current resolution per invoice — drives the reroute control's "currently …"
  // label and the post-reroute draft guard (superseded / rerouted).
  const resolutionByInvoice = useMemo(() => {
    const m = new Map<string, ResolutionDecision>();
    for (const r of results) {
      if (r.resolution) m.set(r.invoice_id, r.resolution);
    }
    return m;
  }, [results]);

  const guardFor = (comm: Communication): DraftGuard =>
    draftGuard(comm.invoiceId ? resolutionByInvoice.get(comm.invoiceId) : undefined);

  // A draft is sendable when it isn't already handled and isn't superseded by a
  // reroute to a no-outreach path.
  const sendable = (comm: Communication): boolean =>
    !isHandled(comm) && guardFor(comm).kind !== 'superseded';

  const [copied, setCopied] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [editedBody, setEditedBody] = useState('');
  const [editedSubject, setEditedSubject] = useState('');
  const [busyId, setBusyId] = useState<string | null>(null);
  const [bulkBusyType, setBulkBusyType] = useState<string | null>(null);
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [approving, setApproving] = useState(false);
  const [feedback, setFeedback] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

  // ---- preview dialog state ----
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewData, setPreviewData] = useState<CommsPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewTitle, setPreviewTitle] = useState('Message preview');

  const handlePreview = async (comm: Communication) => {
    if (!runId || !comm.invoiceId) return;
    setPreviewTitle(`Preview · ${comm.invoiceId}`);
    setPreviewData(null);
    setPreviewError(null);
    setPreviewLoading(true);
    setPreviewOpen(true);
    try {
      setPreviewData(await api.previewDraft(runId, comm.invoiceId));
    } catch (e) {
      setPreviewError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setPreviewLoading(false);
    }
  };

  // Group drafts into the (present) channel tabs.
  const groups = useMemo(() => {
    const map = new Map<Communication['type'], Communication[]>();
    for (const c of communications) {
      const list = map.get(c.type) ?? [];
      list.push(c);
      map.set(c.type, list);
    }
    return TYPE_ORDER.filter((t) => map.has(t)).map((t) => ({
      type: t,
      items: map.get(t)!,
    }));
  }, [communications]);

  if (groups.length === 0) return null;

  const handleCopy = (content: string, id: string) => {
    navigator.clipboard.writeText(content);
    setCopied(id);
    setTimeout(() => setCopied(null), 2000);
  };

  const handleEdit = (comm: Communication) => {
    setEditing(comm.id);
    setEditedBody(comm.content);
    setEditedSubject(comm.subject);
    setFeedback(null);
  };

  const handleSave = async (comm: Communication) => {
    if (!runId || !comm.invoiceId) return;
    setBusyId(comm.id);
    setFeedback(null);
    try {
      await api.patchDraft(runId, comm.invoiceId, {
        body: editedBody,
        subject: editedSubject,
      });
      setEditing(null);
      await reloadData();
      setFeedback({ kind: 'ok', text: `Saved draft for ${comm.invoiceId}.` });
    } catch (e) {
      setFeedback({ kind: 'err', text: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusyId(null);
    }
  };

  const handleSend = async (comm: Communication) => {
    if (!runId || !comm.invoiceId) return;
    const guard = guardFor(comm);
    if (guard.kind === 'superseded') {
      // Defensive — the button is disabled, but never send a draft for an
      // invoice that's been rerouted to a no-outreach path.
      setFeedback({
        kind: 'err',
        text: `${comm.invoiceId} is now ${guard.path} and needs no outreach — sending is disabled.`,
      });
      return;
    }
    // A draft that was already sent and is being sent again is an explicit
    // resend — re-resolve the recipient so an updated vendor email is used.
    const isResend = comm.sendStatus === 'sent' || comm.sendStatus === 'dryrun';
    const override = overrides[comm.id]?.trim() || undefined;
    const destination = override ?? comm.recipient;
    const rerouteWarning =
      guard.kind === 'rerouted'
        ? `\n\n⚠ This invoice was rerouted to ${guard.path} after this draft was written — ` +
          `the message may not match the new decision. Review it before sending.`
        : '';
    const resendNote = isResend
      ? `\n\nThis will RESEND and use the vendor's current email` +
        (override ? '' : ' (from the vendor directory)') +
        `, not the address used last time.`
      : '';
    if (
      !window.confirm(
        `${isResend ? 'Resend' : 'Send'} this ${comm.type.toLowerCase()} for ${comm.invoiceId}?${rerouteWarning}${resendNote}\n\n` +
          `If the backend is in dry-run mode it will be written to artifacts; ` +
          `otherwise it will be dispatched to ${destination}.`,
      )
    )
      return;
    setBusyId(comm.id);
    setFeedback(null);
    try {
      const result = await api.sendDraft(runId, comm.invoiceId, override, isResend);
      await reloadData();
      setFeedback({
        kind: result.status === 'failed' ? 'err' : 'ok',
        text:
          result.status === 'failed'
            ? `Send failed for ${comm.invoiceId}: ${result.error_message ?? 'unknown error'}`
            : `${result.status === 'dryrun' ? 'Dry-run' : 'Sent'} · ${comm.invoiceId} via ${result.provider}.`,
      });
    } catch (e) {
      setFeedback({ kind: 'err', text: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusyId(null);
    }
  };

  const handleSendAll = async (type: Communication['type'], items: Communication[]) => {
    if (!runId) return;
    // Only send drafts that still apply — skip superseded (rerouted-to-no-outreach)
    // and already-handled ones so a bulk send can't fire a stale message.
    const ids = items
      .filter(sendable)
      .map((c) => c.invoiceId)
      .filter((v): v is string => Boolean(v));
    if (ids.length === 0) {
      setFeedback({ kind: 'err', text: `No sendable ${type.toLowerCase()} drafts in this channel.` });
      return;
    }
    const supersededCount = items.filter((c) => guardFor(c).kind === 'superseded').length;
    if (
      !window.confirm(
        `Send ${ids.length} ${type.toLowerCase()} draft(s)?` +
          (supersededCount > 0
            ? `\n\n${supersededCount} rerouted draft(s) that no longer apply will be skipped.`
            : ''),
      )
    )
      return;
    setBulkBusyType(type);
    setFeedback(null);
    // Send in modest batches so a large run (100s of invoices = 100s of emails)
    // never exceeds the request timeout. Each batch's totals accumulate; sends
    // are idempotent on the backend, so if a batch fails the user can click
    // "Send all" again to resume — already-sent drafts are skipped.
    const totals = { sent: 0, dryrun: 0, failed: 0, skipped: 0 };
    let processed = 0;
    try {
      for (let i = 0; i < ids.length; i += SEND_ALL_BATCH_SIZE) {
        const batch = ids.slice(i, i + SEND_ALL_BATCH_SIZE);
        const res = await api.sendAll(runId, batch);
        const s = res.summary;
        totals.sent += s.sent ?? 0;
        totals.dryrun += s.dryrun ?? 0;
        totals.failed += s.failed ?? 0;
        totals.skipped += s.skipped ?? 0;
        processed += batch.length;
        if (ids.length > SEND_ALL_BATCH_SIZE) {
          setFeedback({ kind: 'ok', text: `${type}: sending… ${processed}/${ids.length}` });
        }
      }
      await reloadData();
      setFeedback({
        kind: totals.failed > 0 ? 'err' : 'ok',
        text: `${type}: ${totals.sent} sent, ${totals.dryrun} dry-run, ${totals.failed} failed, ${totals.skipped} skipped.`,
      });
    } catch (e) {
      // Reflect whatever already sent, and tell the user it's resumable.
      await reloadData().catch(() => {});
      const msg = e instanceof ApiError ? e.message : String(e);
      setFeedback({
        kind: 'err',
        text:
          `${type}: stopped after ${processed}/${ids.length} (${msg}). ` +
          `Click "Send all" again to resume — already-sent drafts are skipped.`,
      });
    } finally {
      setBulkBusyType(null);
    }
  };

  const handleApprove = async () => {
    setApproving(true);
    setFeedback(null);
    try {
      await approve();
      setFeedback({ kind: 'ok', text: 'Run approved and marked COMPLETED.' });
    } catch (e) {
      setFeedback({ kind: 'err', text: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setApproving(false);
    }
  };

  return (
    <>
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-4 space-y-0">
        <CardTitle className="flex items-center gap-2">
          <MessageSquare className="w-5 h-5 text-primary" />
          AI-Generated Communications
          <Badge
            variant={communications.every(isHandled) ? 'success' : 'secondary'}
            className="ml-1"
            title="Messages sent (incl. dry-run) of total drafts"
          >
            {communications.filter(isHandled).length}/{communications.length} sent
          </Badge>
        </CardTitle>
        {status === 'AWAITING_REVIEW' && (
          <Button
            onClick={handleApprove}
            disabled={approving || !canApprove}
            title={canApprove ? undefined : 'Your role cannot approve runs'}
            variant="outline"
            className="gap-2"
          >
            {approving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
            Approve run
          </Button>
        )}
      </CardHeader>
      <CardContent>
        {feedback && (
          <div
            className={`mb-4 flex items-start gap-2 p-3 rounded-lg text-sm border ${
              feedback.kind === 'ok'
                ? 'bg-settled/10 border-settled/20 text-settled'
                : 'bg-overdue/10 border-overdue/20 text-overdue'
            }`}
          >
            {feedback.kind === 'ok' ? (
              <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />
            ) : (
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            )}
            <span className="break-words">{feedback.text}</span>
          </div>
        )}

        <Tabs defaultValue={groups[0].type} className="w-full">
          <TabsList
            className="grid w-full mb-4"
            style={{ gridTemplateColumns: `repeat(${groups.length}, minmax(0, 1fr))` }}
          >
            {groups.map(({ type, items }) => {
              const Icon = iconMap[type];
              const remaining = items.filter(sendable).length;
              return (
                <TabsTrigger key={type} value={type} className="gap-2">
                  <Icon className="w-4 h-4" />
                  <span className="hidden sm:inline">{type}</span>
                  {remaining > 0 ? (
                    <Badge variant="secondary" className="ml-1" title={`${remaining} not yet sent`}>
                      {remaining}
                    </Badge>
                  ) : (
                    <Badge variant="success" className="ml-1 gap-1" title="All sent">
                      <CheckCircle2 className="w-3 h-3" />
                    </Badge>
                  )}
                </TabsTrigger>
              );
            })}
          </TabsList>

          {groups.map(({ type, items }) => (
            <TabsContent key={type} value={type} className="space-y-4">
              <div className="flex items-center justify-between">
                <p className="text-sm text-muted-foreground">
                  {items.filter(isHandled).length} of {items.length} sent in this channel
                </p>
                <Button
                  size="sm"
                  variant="outline"
                  className="gap-2"
                  disabled={bulkBusyType === type || !runId || !canSend || !items.some(sendable)}
                  title={canSend ? undefined : 'Your role cannot send communications'}
                  onClick={() => handleSendAll(type, items)}
                >
                  {bulkBusyType === type ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Send className="w-4 h-4" />
                  )}
                  {items.some(sendable)
                    ? 'Send all'
                    : items.every(isHandled)
                      ? 'All sent'
                      : 'Nothing to send'}
                </Button>
              </div>

              {items.map((comm) => {
                const Icon = iconMap[comm.type];
                const isEditing = editing === comm.id;
                const isBusy = busyId === comm.id;
                const alreadySent = comm.sendStatus === 'sent' || comm.sendStatus === 'dryrun';
                const guard = guardFor(comm);
                const isSuppressed = guard.kind === 'superseded';

                return (
                  <motion.div
                    key={comm.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="rounded-xl border bg-card"
                  >
                    <div className="flex items-center gap-3 p-3 border-b bg-muted/40 rounded-t-xl">
                      <Icon className="w-5 h-5 text-muted-foreground shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">{comm.subject}</p>
                        <p className="text-xs text-muted-foreground truncate">
                          {comm.invoiceId && <span className="font-mono">{comm.invoiceId}</span>}
                          {comm.invoiceId && ' · '}To: {comm.recipient}
                        </p>
                      </div>
                      {comm.isEdited && (
                        <Badge variant="secondary" className="hidden sm:inline-flex">Edited</Badge>
                      )}
                      {guard.kind === 'superseded' && (
                        <Badge
                          variant="warning"
                          title={`Rerouted to ${guard.path}, which needs no outreach`}
                        >
                          No longer applies
                        </Badge>
                      )}
                      {guard.kind === 'rerouted' && (
                        <Badge
                          variant="warning"
                          title={`Rerouted to ${guard.path} after this draft was written`}
                        >
                          Rerouted
                        </Badge>
                      )}
                      {(comm.channel === 'slack' || comm.channel === 'finance_note') &&
                        (slackConnected ? (
                          <Badge
                            variant="secondary"
                            className="hidden gap-1 sm:inline-flex"
                            title="Posts to your Slack channel on a live send."
                          >
                            <MessageSquare className="w-3 h-3" /> Slack
                          </Badge>
                        ) : (
                          <Badge
                            variant="warning"
                            className="hidden gap-1 sm:inline-flex"
                            title="Slack isn't connected, so this will be emailed instead. Connect Slack in Settings → Integrations."
                          >
                            <Mail className="w-3 h-3" /> Email · no Slack
                          </Badge>
                        ))}
                      <StatusBadge status={comm.sendStatus} />
                    </div>

                    <div className="p-4 space-y-3">
                      {isEditing ? (
                        <>
                          <div className="space-y-1">
                            <label className="text-xs font-medium text-muted-foreground">Subject</label>
                            <Input
                              value={editedSubject}
                              onChange={(e) => setEditedSubject(e.target.value)}
                            />
                          </div>
                          <div className="space-y-1">
                            <label className="text-xs font-medium text-muted-foreground">Body</label>
                            <Textarea
                              value={editedBody}
                              onChange={(e) => setEditedBody(e.target.value)}
                              className="min-h-[200px] font-mono text-sm"
                            />
                          </div>
                          <div className="flex gap-2">
                            <Button onClick={() => handleSave(comm)} disabled={isBusy} className="gap-2">
                              {isBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                              Save Changes
                            </Button>
                            <Button variant="outline" onClick={() => setEditing(null)} disabled={isBusy}>
                              Cancel
                            </Button>
                          </div>
                        </>
                      ) : (
                        <>
                          <div className="p-4 rounded-lg border bg-muted/40">
                            <pre className="whitespace-pre-wrap text-sm text-foreground/80 font-mono leading-relaxed">
                              {comm.content}
                            </pre>
                          </div>
                          {guard.kind === 'superseded' && (
                            <p className="flex items-start gap-1.5 rounded-lg border border-pending/25 bg-pending/10 p-2.5 text-xs text-pending">
                              <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                              <span>
                                This invoice was rerouted to{' '}
                                <span className="font-medium">{guard.path}</span>, which needs no
                                outreach — sending is disabled. Reroute it back to a comms path if
                                that was a mistake.
                              </span>
                            </p>
                          )}
                          {guard.kind === 'rerouted' && (
                            <p className="flex items-start gap-1.5 rounded-lg border border-pending/25 bg-pending/10 p-2.5 text-xs text-pending">
                              <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                              <span>
                                Rerouted to <span className="font-medium">{guard.path}</span> after
                                this draft was written — review or edit it before sending.
                              </span>
                            </p>
                          )}
                          <div className="space-y-1">
                            <label className="text-xs font-medium text-muted-foreground">
                              Recipient override (optional)
                            </label>
                            <Input
                              value={overrides[comm.id] ?? ''}
                              onChange={(e) =>
                                setOverrides((o) => ({ ...o, [comm.id]: e.target.value }))
                              }
                              placeholder={comm.recipient}
                              className="h-8 text-xs"
                            />
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handlePreview(comm)}
                              disabled={!runId}
                              className="gap-2"
                            >
                              <Eye className="w-4 h-4" />
                              Preview
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleCopy(comm.content, comm.id)}
                              className="gap-2"
                            >
                              {copied === comm.id ? (
                                <><Check className="w-4 h-4 text-settled" />Copied!</>
                              ) : (
                                <><Copy className="w-4 h-4" />Copy</>
                              )}
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleEdit(comm)}
                              disabled={isBusy || !canEdit}
                              title={canEdit ? undefined : 'Your role cannot edit drafts'}
                              className="gap-2"
                            >
                              <Edit className="w-4 h-4" />
                              Edit
                            </Button>
                            <Button
                              size="sm"
                              onClick={() => handleSend(comm)}
                              disabled={isBusy || !runId || !canSend || isSuppressed}
                              title={
                                isSuppressed
                                  ? 'This invoice was rerouted to a path that needs no outreach'
                                  : canSend
                                    ? undefined
                                    : 'Your role cannot send communications'
                              }
                              className="gap-2 ml-auto"
                            >
                              {isBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                              {alreadySent ? 'Resend' : 'Send'}
                            </Button>
                          </div>
                          <RerouteControl
                            runId={runId}
                            invoiceId={comm.invoiceId}
                            currentPath={
                              comm.invoiceId
                                ? resolutionByInvoice.get(comm.invoiceId)?.resolution_path
                                : undefined
                            }
                            disabled={!canEdit}
                            onDone={(m) => {
                              setFeedback(m);
                              if (m.kind === 'ok') void reloadData();
                            }}
                          />
                        </>
                      )}
                    </div>
                  </motion.div>
                );
              })}
            </TabsContent>
          ))}
        </Tabs>
      </CardContent>
    </Card>
    <CommsPreviewDialog
      open={previewOpen}
      onOpenChange={setPreviewOpen}
      title={previewTitle}
      preview={previewData}
      loading={previewLoading}
      error={previewError}
    />
    </>
  );
}
