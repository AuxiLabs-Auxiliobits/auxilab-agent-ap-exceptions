import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  KeyRound,
  Loader2,
  CheckCircle2,
  AlertCircle,
  ShieldAlert,
  Trash2,
  Plug,
  Link2,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  api,
  ApiError,
  type IntegrationInput,
  type IntegrationKind,
  type IntegrationsResponse,
  type IntegrationStatus,
} from '@/lib/api';

interface ProviderDef {
  kind: IntegrationKind;
  label: string;
  keyLabel: string;
  fields: { name: keyof IntegrationInput; label: string; placeholder: string }[];
  oauth?: 'google' | 'slack'; // show a "Connect via OAuth" button
}

interface SectionDef {
  title: string;
  providers: ProviderDef[];
}

const SECTIONS: SectionDef[] = [
  {
    title: 'AI provider',
    providers: [
      {
        kind: 'ai_anthropic',
        label: 'Anthropic (Claude)',
        keyLabel: 'API key',
        fields: [
          { name: 'classify_model', label: 'Classify model', placeholder: 'claude-opus-4-8' },
          { name: 'draft_model', label: 'Draft model', placeholder: 'claude-sonnet-4-6' },
        ],
      },
      {
        kind: 'ai_gemini',
        label: 'Google Gemini',
        keyLabel: 'API key',
        fields: [
          { name: 'classify_model', label: 'Classify model', placeholder: 'gemini-2.5-flash' },
          { name: 'draft_model', label: 'Draft model', placeholder: 'gemini-2.5-flash' },
        ],
      },
      {
        kind: 'ai_azure',
        label: 'Azure OpenAI',
        keyLabel: 'API key',
        fields: [
          { name: 'endpoint', label: 'Endpoint', placeholder: 'https://<resource>.openai.azure.com/' },
          { name: 'deployment', label: 'Deployment', placeholder: 'gpt-4o-mini' },
          { name: 'api_version', label: 'API version', placeholder: '2024-10-21' },
        ],
      },
    ],
  },
  {
    title: 'Email & Slack',
    providers: [
      {
        kind: 'email',
        label: 'Email (SMTP or Gmail OAuth)',
        keyLabel: 'SMTP password',
        oauth: 'google',
        fields: [
          { name: 'from_address', label: 'From address', placeholder: 'ap@yourcompany.com' },
          { name: 'smtp_host', label: 'SMTP host', placeholder: 'smtp.gmail.com' },
          { name: 'smtp_port', label: 'SMTP port', placeholder: '587' },
        ],
      },
      {
        kind: 'slack',
        label: 'Slack (webhook or app)',
        keyLabel: 'Incoming webhook URL',
        oauth: 'slack',
        fields: [],
      },
    ],
  },
];

function ProviderCard({
  def,
  status,
  disabled,
  oauthConfigured,
  onChanged,
}: {
  def: ProviderDef;
  status: IntegrationStatus | undefined;
  disabled: boolean;
  /** Whether the server has registered this provider's OAuth app. Only
   *  meaningful when `def.oauth` is set; gates the "Connect" button. */
  oauthConfigured: boolean;
  onChanged: () => void;
}) {
  const configured = !!status?.configured;
  const [secret, setSecret] = useState('');
  const [meta, setMeta] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<'save' | 'test' | 'remove' | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  // Seed model/meta fields from the stored (non-secret) meta.
  useEffect(() => {
    setMeta((status?.meta as Record<string, string>) ?? {});
  }, [status]);

  const save = async () => {
    setBusy('save');
    setMsg(null);
    try {
      const body: IntegrationInput = {};
      Object.assign(body, meta); // meta keys map 1:1 to IntegrationInput meta fields
      if (secret.trim()) body.secret = secret.trim();
      await api.putIntegration(def.kind, body);
      setSecret('');
      setMsg({ ok: true, text: 'Saved.' });
      onChanged();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  };

  const test = async () => {
    setBusy('test');
    setMsg(null);
    try {
      const r = await api.testIntegration(def.kind);
      setMsg({ ok: r.ok, text: r.detail });
    } catch (e) {
      setMsg({ ok: false, text: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  };

  const connectOAuth = async () => {
    if (!def.oauth) return;
    setBusy('save');
    setMsg(null);
    try {
      const { auth_url } = await api.oauthConnect(def.oauth);
      window.location.href = auth_url; // hand off to the provider's consent screen
    } catch (e) {
      setMsg({ ok: false, text: e instanceof ApiError ? e.message : String(e) });
      setBusy(null);
    }
  };

  const remove = async () => {
    if (!window.confirm(`Remove ${def.label} credentials for this organization?`)) return;
    setBusy('remove');
    setMsg(null);
    try {
      await api.deleteIntegration(def.kind);
      setMsg({ ok: true, text: 'Removed.' });
      onChanged();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="rounded-lg border p-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium">{def.label}</span>
        {configured ? (
          <Badge variant="success" className="gap-1"><CheckCircle2 className="w-3 h-3" /> Configured</Badge>
        ) : (
          <Badge variant="secondary">Not set</Badge>
        )}
      </div>

      <label className="space-y-1 block">
        <span className="text-xs font-medium text-muted-foreground">
          {def.keyLabel} {configured && <span className="text-muted-foreground/70">— stored; enter a new value to replace</span>}
        </span>
        <Input
          type="password"
          autoComplete="off"
          value={secret}
          onChange={(e) => setSecret(e.target.value)}
          placeholder={configured ? '•••••••••••• (stored)' : `Paste ${def.keyLabel}`}
          disabled={disabled}
        />
      </label>

      <div className="grid gap-2 sm:grid-cols-2">
        {def.fields.map((f) => (
          <label key={String(f.name)} className="space-y-1">
            <span className="text-xs font-medium text-muted-foreground">{f.label}</span>
            <Input
              value={meta[f.name as string] ?? ''}
              onChange={(e) => setMeta((m) => ({ ...m, [f.name as string]: e.target.value }))}
              placeholder={f.placeholder}
              disabled={disabled}
              className="h-8 text-xs"
            />
          </label>
        ))}
      </div>

      {msg && (
        <p className={`text-xs ${msg.ok ? 'text-settled' : 'text-overdue'} break-words`}>{msg.text}</p>
      )}

      {def.oauth && (
        <p className="text-xs text-muted-foreground">
          {oauthConfigured
            ? `Or connect via OAuth (recommended) — no ${def.oauth === 'google' ? 'password' : 'webhook'} to paste.`
            : `One-click ${def.oauth === 'google' ? 'Gmail' : 'Slack'} connect is coming soon — for now use the ${def.keyLabel.toLowerCase()} above.`}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {def.oauth &&
          (oauthConfigured ? (
            <Button size="sm" variant="secondary" onClick={connectOAuth} disabled={busy !== null} className="gap-2">
              <Link2 className="w-4 h-4" />
              Connect {def.oauth === 'google' ? 'Gmail' : 'Slack'}
            </Button>
          ) : (
            // Not configured on the server → disable and explain via tooltip.
            // The span wrapper lets the tooltip fire even though the button is disabled.
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span tabIndex={0} className="inline-flex">
                    <Button size="sm" variant="secondary" disabled className="gap-2 pointer-events-none">
                      <Link2 className="w-4 h-4" />
                      Connect {def.oauth === 'google' ? 'Gmail' : 'Slack'}
                      <Badge variant="secondary" className="ml-1">Soon</Badge>
                    </Button>
                  </span>
                </TooltipTrigger>
                <TooltipContent className="max-w-xs">
                  Coming soon — {def.oauth === 'google' ? 'Google' : 'Slack'} OAuth isn&apos;t configured on
                  the server yet ({def.oauth === 'google' ? 'GOOGLE_OAUTH_*' : 'SLACK_CLIENT_*'}). Use the{' '}
                  {def.keyLabel.toLowerCase()} field above instead.
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          ))}
        <Button size="sm" onClick={save} disabled={disabled || busy !== null} className="gap-2">
          {busy === 'save' ? <Loader2 className="w-4 h-4 animate-spin" /> : <KeyRound className="w-4 h-4" />}
          Save
        </Button>
        {configured && (
          <Button size="sm" variant="outline" onClick={test} disabled={busy !== null} className="gap-2">
            {busy === 'test' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plug className="w-4 h-4" />}
            Test
          </Button>
        )}
        {configured && (
          <Button size="sm" variant="outline" onClick={remove} disabled={busy !== null} className="gap-2 text-overdue">
            {busy === 'remove' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
            Remove
          </Button>
        )}
      </div>
    </div>
  );
}

export function IntegrationsPanel() {
  const [data, setData] = useState<IntegrationsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      setData(await api.listIntegrations());
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const byKind = useMemo(() => {
    const m = new Map<string, IntegrationStatus>();
    (data?.integrations ?? []).forEach((i) => m.set(i.kind, i));
    return m;
  }, [data]);

  const encMissing = data ? !data.enc_key_configured : false;
  const flagOff = data ? !data.per_org_config_enabled : false;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Plug className="w-5 h-5 text-primary" />
          Integrations (BYOK)
          <Badge variant="secondary" className="ml-1 font-normal">admin</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          Configure this organization&apos;s own AI provider, email sender, and Slack. Secrets are
          encrypted at rest and never shown again. Each organization&apos;s credentials are isolated
          to its own runs.
        </p>

        {loading && (
          <div className="space-y-3" aria-busy="true">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="space-y-2 rounded-lg border p-3">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-9 w-full" />
              </div>
            ))}
          </div>
        )}
        {error && <p className="text-sm text-overdue">Could not load integrations: {error}</p>}

        {data && (
          <>
            {encMissing && (
              <div className="flex items-start gap-2 rounded-lg border border-overdue/25 bg-overdue/10 p-3 text-sm text-overdue">
                <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
                <span>
                  Server has no <code>CONFIG_ENC_KEY</code> — credentials can&apos;t be stored
                  securely yet. Set it on the backend, then configure providers here.
                </span>
              </div>
            )}
            {flagOff && (
              <div className="flex items-start gap-2 rounded-lg border border-pending/25 bg-pending/10 p-3 text-sm text-pending">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>
                  Per-org config is off (<code>PER_ORG_CONFIG_ENABLED=false</code>). You can save keys
                  now, but runs won&apos;t use them until it&apos;s enabled on the backend.
                </span>
              </div>
            )}

            {SECTIONS.map((section) => (
              <div key={section.title} className="space-y-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {section.title}
                </p>
                {section.providers.map((def) => (
                  <ProviderCard
                    key={def.kind}
                    def={def}
                    status={byKind.get(def.kind)}
                    disabled={encMissing}
                    oauthConfigured={
                      def.oauth === 'google'
                        ? !!data.google_oauth_configured
                        : def.oauth === 'slack'
                          ? !!data.slack_oauth_configured
                          : false
                    }
                    onChanged={load}
                  />
                ))}
              </div>
            ))}

            <div className="border-t pt-3">
              <Link to="/newsletter" className="text-sm text-primary hover:underline">
                Compose &amp; send a newsletter →
              </Link>
              <span className="ml-2 text-xs text-muted-foreground">(platform operator · needs the newsletter token)</span>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
