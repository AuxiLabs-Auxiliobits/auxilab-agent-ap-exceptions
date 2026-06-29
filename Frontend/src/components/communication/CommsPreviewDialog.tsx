import { Mail, MessageSquare, AlertCircle } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import type { CommsPreview, SlackBlock } from '@/lib/api';

/**
 * Renders a tiny subset of Slack mrkdwn (`*bold*`, `` `code` ``) as React nodes.
 * Everything else is plain text; newlines are preserved by the wrapping element.
 */
function renderMrkdwn(text: string) {
  const parts = text.split(/(\*[^*]+\*|`[^`]+`)/g);
  return parts.map((p, i) => {
    if (/^\*[^*]+\*$/.test(p)) return <strong key={i}>{p.slice(1, -1)}</strong>;
    if (/^`[^`]+`$/.test(p))
      return (
        <code key={i} className="rounded bg-black/5 px-1 py-0.5 text-[13px]">
          {p.slice(1, -1)}
        </code>
      );
    return <span key={i}>{p}</span>;
  });
}

/** A lightweight, Slack-like rendering of the Block Kit payload. */
function SlackPreview({ blocks }: { blocks: SlackBlock[] }) {
  return (
    <div className="rounded-lg border bg-white p-4 text-[#1d1c1d] shadow-sm">
      <div className="flex items-start gap-3">
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded bg-[#4a154b] text-sm font-bold text-white">
          AP
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <span className="text-[15px] font-bold">AP Exception Agent</span>
            <span className="rounded bg-black/5 px-1 text-[11px] text-gray-500">APP</span>
          </div>
          <div className="mt-1 space-y-2">
            {blocks.map((b, i) => {
              if (b.type === 'header') {
                return (
                  <div key={i} className="text-[15px] font-bold leading-snug">
                    {b.text?.text}
                  </div>
                );
              }
              if (b.type === 'divider') {
                return <hr key={i} className="border-black/10" />;
              }
              if (b.type === 'section' && b.fields) {
                return (
                  <div key={i} className="grid grid-cols-2 gap-x-4 gap-y-1 text-[13px]">
                    {b.fields.map((f, j) => (
                      <div key={j} className="whitespace-pre-wrap leading-snug">
                        {renderMrkdwn(f.text)}
                      </div>
                    ))}
                  </div>
                );
              }
              if (b.type === 'section' && b.text) {
                return (
                  <div key={i} className="whitespace-pre-wrap text-[14px] leading-relaxed">
                    {renderMrkdwn(b.text.text)}
                  </div>
                );
              }
              if (b.type === 'context') {
                return (
                  <div key={i} className="whitespace-pre-wrap text-[12px] text-gray-500">
                    {renderMrkdwn((b.elements ?? []).map((e) => e.text).join('  '))}
                  </div>
                );
              }
              return null;
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

interface CommsPreviewDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title?: string;
  preview: CommsPreview | null;
  loading?: boolean;
  error?: string | null;
}

export function CommsPreviewDialog({
  open,
  onOpenChange,
  title = 'Message preview',
  preview,
  loading,
  error,
}: CommsPreviewDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            Exactly how this message renders — nothing is sent. Switch tabs to see the
            email and Slack representations.
          </DialogDescription>
        </DialogHeader>

        {loading && (
          <div className="space-y-3 py-2" aria-busy="true">
            <Skeleton className="h-9 w-48" />
            <Skeleton className="h-4 w-64" />
            <Skeleton className="h-72 w-full rounded-lg" />
          </div>
        )}

        {!loading && error && (
          <div className="flex items-start gap-2 rounded-lg border border-overdue/25 bg-overdue/10 p-3 text-sm text-overdue">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span className="break-words">{error}</span>
          </div>
        )}

        {!loading && !error && preview && (
          <Tabs defaultValue="email" className="w-full">
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="email" className="gap-2">
                <Mail className="h-4 w-4" /> Email
              </TabsTrigger>
              <TabsTrigger value="slack" className="gap-2">
                <MessageSquare className="h-4 w-4" /> Slack
              </TabsTrigger>
            </TabsList>

            <TabsContent value="email" className="space-y-2">
              {preview.subject && (
                <p className="text-sm">
                  <span className="text-muted-foreground">Subject: </span>
                  <span className="font-medium">{preview.subject}</span>
                </p>
              )}
              <iframe
                title="Email preview"
                srcDoc={preview.email.html}
                sandbox=""
                className="h-[460px] w-full rounded-lg border bg-white"
              />
            </TabsContent>

            <TabsContent value="slack">
              <SlackPreview blocks={preview.slack.blocks} />
            </TabsContent>
          </Tabs>
        )}
      </DialogContent>
    </Dialog>
  );
}
