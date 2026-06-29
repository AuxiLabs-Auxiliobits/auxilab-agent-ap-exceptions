import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Sparkles, X, Send, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { useRun } from '@/hooks/useRun';
import { api, ApiError, type AskResult } from '@/lib/api';

interface Msg {
  role: 'user' | 'desk';
  text: string;
  cited?: string[];
}

const SUGGESTIONS = [
  'What needs follow-up today?',
  "What's at risk?",
  'Which vendors have the most exceptions?',
  'Give me a summary',
];

/**
 * "Ask the desk" — a floating, read-only assistant. It answers ONLY from the
 * active run's real data (grounded server-side), so it can't invent figures and
 * never takes actions. Available on every authenticated page.
 */
export function AskDesk() {
  const { runId } = useRun();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, busy]);

  const send = async (q?: string) => {
    const question = (q ?? input).trim();
    if (!question || busy || !runId) return;
    setMessages((m) => [...m, { role: 'user', text: question }]);
    setInput('');
    setBusy(true);
    try {
      const res: AskResult = await api.askDesk(runId, question);
      setMessages((m) => [...m, { role: 'desk', text: res.answer, cited: res.cited_invoice_ids }]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: 'desk', text: e instanceof ApiError ? e.message : 'Something went wrong — please try again.' },
      ]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      {/* Launcher */}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? 'Close assistant' : 'Ask the desk'}
        className="fixed bottom-6 right-6 z-50 grid h-12 w-12 place-items-center rounded-full bg-primary text-primary-foreground shadow-lg transition-transform hover:scale-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {open ? <X className="h-5 w-5" /> : <Sparkles className="h-5 w-5" />}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 16, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 16, scale: 0.98 }}
            transition={{ duration: 0.18 }}
            className="fixed bottom-24 right-6 z-50 flex h-[520px] max-h-[72vh] w-[380px] max-w-[calc(100vw-3rem)] flex-col overflow-hidden rounded-2xl border bg-card shadow-2xl"
          >
            {/* Header */}
            <div className="flex items-center gap-2 border-b bg-muted/40 px-4 py-3">
              <Sparkles className="h-4 w-4 text-primary" />
              <div className="min-w-0">
                <p className="text-sm font-semibold leading-tight">Ask the desk</p>
                <p className="text-[11px] text-muted-foreground leading-tight">
                  Read-only · answers only from this run’s data
                </p>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close"
                className="ml-auto grid h-7 w-7 place-items-center rounded text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Messages */}
            <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
              {messages.length === 0 && (
                <div className="space-y-3">
                  <p className="text-sm text-muted-foreground">
                    {runId
                      ? 'Ask about the current run — follow-ups, SLA risk, escalations, vendors, or a specific invoice.'
                      : 'Open or upload a run first, then ask me about it.'}
                  </p>
                  {runId && (
                    <div className="flex flex-wrap gap-2">
                      {SUGGESTIONS.map((s) => (
                        <button
                          key={s}
                          type="button"
                          onClick={() => void send(s)}
                          className="rounded-full border px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {messages.map((m, i) => (
                <div key={i} className={m.role === 'user' ? 'flex justify-end' : 'flex justify-start'}>
                  <div
                    className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${
                      m.role === 'user'
                        ? 'bg-primary text-primary-foreground'
                        : 'border bg-muted/40 text-foreground'
                    }`}
                  >
                    <p className="whitespace-pre-wrap break-words leading-relaxed">{m.text}</p>
                    {m.cited && m.cited.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {m.cited.map((id) => (
                          <Badge key={id} variant="secondary" className="font-mono text-[10px]">
                            {id}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {busy && (
                <div className="flex justify-start">
                  <div className="rounded-xl border bg-muted/40 px-3 py-2">
                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                  </div>
                </div>
              )}
            </div>

            {/* Composer */}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void send();
              }}
              className="flex items-center gap-2 border-t p-3"
            >
              <Input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={runId ? 'Ask about this run…' : 'No active run'}
                disabled={!runId || busy}
                className="h-9"
              />
              <Button type="submit" size="icon" className="h-9 w-9 shrink-0" disabled={!runId || busy || !input.trim()}>
                <Send className="h-4 w-4" />
              </Button>
            </form>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
