import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Loader2, Eye, Send, RefreshCw, CheckCircle2, AlertCircle, Mail, ArrowLeft } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { api, ApiError } from '@/lib/api';

const TOKEN_KEY = 'newsletter-admin-token';

/**
 * Platform-operator newsletter composer. Not part of the org RBAC — the
 * NEWSLETTER_ADMIN_TOKEN is the gate (sent as X-Newsletter-Token). Reachable at
 * /newsletter (not in the app nav). Compose → preview → dry-run → send to all.
 */
export function NewsletterPage() {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) ?? '');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [stats, setStats] = useState<{ active: number; total: number; unsubscribed: number } | null>(null);
  const [previewHtml, setPreviewHtml] = useState<string | null>(null);
  const [busy, setBusy] = useState<'stats' | 'preview' | 'dry' | 'send' | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const loadStats = async (tok = token) => {
    if (!tok.trim()) return;
    setBusy('stats');
    setMsg(null);
    try {
      setStats(await api.newsletterStats(tok.trim()));
    } catch (e) {
      setStats(null);
      setMsg({ ok: false, text: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  };

  // Auto-load counts if a token was remembered.
  useEffect(() => {
    if (token.trim()) void loadStats(token);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const rememberToken = (t: string) => {
    setToken(t);
    if (t.trim()) localStorage.setItem(TOKEN_KEY, t.trim());
    else localStorage.removeItem(TOKEN_KEY);
  };

  const preview = async () => {
    setBusy('preview');
    setMsg(null);
    try {
      const { html } = await api.newsletterPreview(token.trim(), subject, body);
      setPreviewHtml(html);
    } catch (e) {
      setMsg({ ok: false, text: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  };

  const run = async (dryRun: boolean) => {
    if (!subject.trim() || !body.trim()) {
      setMsg({ ok: false, text: 'Subject and body are required.' });
      return;
    }
    if (!dryRun) {
      const n = stats?.active ?? 0;
      if (!window.confirm(`Send this newsletter to ${n} active subscriber(s)? This cannot be undone.`)) return;
    }
    setBusy(dryRun ? 'dry' : 'send');
    setMsg(null);
    try {
      const r = await api.sendNewsletter(token.trim(), subject, body, dryRun);
      if (r.dry_run) {
        setMsg({ ok: true, text: `Dry run — would send to ${r.recipients} subscriber(s). Nothing sent.` });
      } else {
        setMsg({
          ok: r.failed === 0,
          text: `Sent ${r.sent}/${r.recipients}${r.failed ? `, ${r.failed} failed` : ''}${
            r.capped_out ? ` (${r.capped_out} over the per-send cap were skipped)` : ''
          }.`,
        });
        void loadStats();
      }
    } catch (e) {
      setMsg({ ok: false, text: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="min-h-screen bg-background p-6">
      <div className="mx-auto max-w-3xl space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="font-display text-2xl font-semibold tracking-tight flex items-center gap-2">
              <Mail className="h-6 w-6 text-primary" /> Newsletter
            </h1>
            <p className="text-sm text-muted-foreground">
              Platform-operator only. Compose and send to all active subscribers.
            </p>
          </div>
          <Link to="/settings" className="text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1">
            <ArrowLeft className="h-4 w-4" /> Settings
          </Link>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Access</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <label className="space-y-1 block">
              <span className="text-xs font-medium text-muted-foreground">Newsletter admin token</span>
              <div className="flex gap-2">
                <Input
                  type="password"
                  value={token}
                  onChange={(e) => rememberToken(e.target.value)}
                  placeholder="NEWSLETTER_ADMIN_TOKEN"
                  autoComplete="off"
                />
                <Button variant="outline" onClick={() => loadStats()} disabled={!token.trim() || busy !== null} className="gap-2 shrink-0">
                  {busy === 'stats' ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                  Check
                </Button>
              </div>
            </label>
            {stats && (
              <div className="flex gap-2 text-sm">
                <Badge variant="success">{stats.active} active</Badge>
                <Badge variant="secondary">{stats.unsubscribed} unsubscribed</Badge>
                <Badge variant="secondary">{stats.total} total</Badge>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Compose</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <label className="space-y-1 block">
              <span className="text-xs font-medium text-muted-foreground">Subject</span>
              <Input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="June product update" />
            </label>
            <label className="space-y-1 block">
              <span className="text-xs font-medium text-muted-foreground">Body</span>
              <Textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                placeholder={"Write your update…\n\n- Bullets become a list\n- Links auto-link\n\nThanks,"}
                className="min-h-[200px] font-mono text-sm"
              />
            </label>

            {msg && (
              <div
                className={`flex items-start gap-2 rounded-lg border p-3 text-sm ${
                  msg.ok ? 'border-settled/20 bg-settled/10 text-settled' : 'border-overdue/20 bg-overdue/10 text-overdue'
                }`}
              >
                {msg.ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /> : <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />}
                <span className="break-words">{msg.text}</span>
              </div>
            )}

            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={preview} disabled={!token.trim() || busy !== null} className="gap-2">
                {busy === 'preview' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />}
                Preview
              </Button>
              <Button variant="outline" onClick={() => run(true)} disabled={!token.trim() || busy !== null} className="gap-2">
                {busy === 'dry' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                Send test (dry run)
              </Button>
              <Button onClick={() => run(false)} disabled={!token.trim() || busy !== null} className="gap-2 ml-auto">
                {busy === 'send' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                Send to all{stats ? ` (${stats.active})` : ''}
              </Button>
            </div>
          </CardContent>
        </Card>

        {previewHtml && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Preview</CardTitle>
            </CardHeader>
            <CardContent>
              <iframe
                title="Newsletter preview"
                srcDoc={previewHtml}
                sandbox=""
                className="h-[480px] w-full rounded-lg border bg-white"
              />
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
