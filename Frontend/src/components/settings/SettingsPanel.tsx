import { useEffect, useState } from 'react';
import {
  Server,
  Cpu,
  Palette,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Save,
  ShieldCheck,
  ShieldAlert,
  Mail,
  MessageSquare,
  Eye,
  Paintbrush,
  Plug,
  Building2,
  SlidersHorizontal,
  ScrollText,
} from 'lucide-react';
import { OrganizationProfile } from '@clerk/react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  api,
  ApiError,
  API_BASE_URL,
  type BackendConfig,
  type CommChannel,
  type CommsPreview,
} from '@/lib/api';
import { CommsPreviewDialog } from '@/components/communication/CommsPreviewDialog';
import { IntegrationsPanel } from '@/components/settings/IntegrationsPanel';
import { RulesPanel } from '@/components/settings/RulesPanel';
import { usePermissions } from '@/hooks/usePermissions';
import { useTheme } from '@/hooks/useTheme';
import { usePreferences, DEFAULT_PREFERENCES } from '@/hooks/usePreferences';

type HealthState =
  | { kind: 'idle' }
  | { kind: 'checking' }
  | { kind: 'ok'; ms: number }
  | { kind: 'fail'; message: string };

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2 border-b border-border/50 last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-sm font-medium text-right">{children}</span>
    </div>
  );
}

const SAMPLE_BODY = `Dear Vendor,

We are reviewing invoice INV-2001 and found a price variance against the purchase order.

- Invoiced unit price exceeds the PO by 14% on 3 line items
- Quantity and totals otherwise match the goods receipt

Could you confirm the correct pricing or issue a corrected invoice?

Thank you,`;

export function SettingsPanel() {
  const { theme, setTheme } = useTheme();
  const { preferences, setPreferences, reset } = usePreferences();
  const { can } = usePermissions();
  const canManageIntegrations = can('config:write');

  // ---- branding/template preview playground (preview-only; not persisted) ----
  const [brandChannel, setBrandChannel] = useState<CommChannel>('vendor_email');
  const [sigName, setSigName] = useState('');
  const [sigTeam, setSigTeam] = useState('');
  const [sigCompany, setSigCompany] = useState('');
  const [sigDisclaimer, setSigDisclaimer] = useState('');
  const [discloseAi, setDiscloseAi] = useState(false);
  const [brandColor, setBrandColor] = useState('');
  const [logoUrl, setLogoUrl] = useState('');
  const [sampleBody, setSampleBody] = useState(SAMPLE_BODY);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewData, setPreviewData] = useState<CommsPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [brandSaving, setBrandSaving] = useState(false);
  const [brandMsg, setBrandMsg] = useState<{ ok: boolean; text: string } | null>(null);

  // Load saved per-org branding so the fields reflect what's persisted (admins only).
  useEffect(() => {
    if (!canManageIntegrations) return;
    void (async () => {
      try {
        const res = await api.listIntegrations();
        const b = res.integrations.find((i) => i.kind === 'branding');
        if (b) {
          const m = b.meta as Record<string, string>;
          if (m.signature_name) setSigName(m.signature_name);
          if (m.signature_team) setSigTeam(m.signature_team);
          if (m.signature_company) setSigCompany(m.signature_company);
          if (m.signature_disclaimer) setSigDisclaimer(m.signature_disclaimer);
          if (m.brand_color) setBrandColor(m.brand_color);
          if (m.logo_url) setLogoUrl(m.logo_url);
          setDiscloseAi(String(m.disclose_ai) === 'true');
        }
      } catch {
        /* non-fatal — keep defaults */
      }
    })();
  }, [canManageIntegrations]);

  const handleBrandSave = async () => {
    setBrandSaving(true);
    setBrandMsg(null);
    try {
      await api.putIntegration('branding', {
        signature_name: sigName || undefined,
        signature_team: sigTeam || undefined,
        signature_company: sigCompany || undefined,
        signature_disclaimer: sigDisclaimer || undefined,
        disclose_ai: discloseAi,
        brand_color: brandColor || undefined,
        logo_url: logoUrl || undefined,
      });
      setBrandMsg({ ok: true, text: 'Saved for this organization.' });
    } catch (e) {
      setBrandMsg({ ok: false, text: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBrandSaving(false);
    }
  };

  const handleBrandPreview = async () => {
    setPreviewData(null);
    setPreviewError(null);
    setPreviewLoading(true);
    setPreviewOpen(true);
    try {
      setPreviewData(
        await api.previewComms({
          channel: brandChannel,
          body: sampleBody,
          signature_name: sigName || null,
          signature_team: sigTeam || null,
          signature_company: sigCompany || null,
          signature_disclaimer: sigDisclaimer || null,
          disclose_ai_assistance: discloseAi,
          brand_color: brandColor || null,
          logo_url: logoUrl || null,
        }),
      );
    } catch (e) {
      setPreviewError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setPreviewLoading(false);
    }
  };

  // ---- backend config (read-only) ----
  const [config, setConfig] = useState<BackendConfig | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthState>({ kind: 'idle' });

  // ---- editable UI preferences (draft until "Save") ----
  const [draftTheme, setDraftTheme] = useState(theme);
  const [draftPageSize, setDraftPageSize] = useState(String(preferences.pageSize));
  const [saved, setSaved] = useState(false);

  const dirty =
    draftTheme !== theme ||
    draftPageSize !== String(preferences.pageSize);

  const loadConfig = async () => {
    setConfigError(null);
    try {
      setConfig(await api.getConfig());
    } catch (e) {
      setConfig(null);
      setConfigError(e instanceof ApiError ? e.message : String(e));
    }
  };

  const testConnection = async () => {
    setHealth({ kind: 'checking' });
    const start = performance.now();
    try {
      await api.health();
      setHealth({ kind: 'ok', ms: Math.round(performance.now() - start) });
      void loadConfig();
    } catch (e) {
      setHealth({ kind: 'fail', message: e instanceof ApiError ? e.message : String(e) });
    }
  };

  useEffect(() => {
    void testConnection();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSave = () => {
    setTheme(draftTheme);
    setPreferences({ pageSize: Number(draftPageSize) });
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  };

  const handleRestoreDefaults = () => {
    reset();
    setTheme('system');
    setDraftTheme('system');
    setDraftPageSize(String(DEFAULT_PREFERENCES.pageSize));
  };

  // One Settings entry, split into role-gated tabs (general / integrations /
  // branding / organization) — keeps secrets in a focused, admin-only context.
  const tabs = [
    { value: 'general', label: 'General', icon: SlidersHorizontal },
    ...(canManageIntegrations ? [{ value: 'integrations', label: 'Integrations', icon: Plug }] : []),
    // Per-org rulebook editor is admin-only — same gate as Integrations.
    ...(canManageIntegrations ? [{ value: 'rules', label: 'Rules', icon: ScrollText }] : []),
    { value: 'branding', label: 'Branding', icon: Paintbrush },
    // Organization (member/role management) is admin-only — same gate as Integrations.
    ...(canManageIntegrations ? [{ value: 'organization', label: 'Organization', icon: Building2 }] : []),
  ];

  return (
    <div className="space-y-6">
      <Tabs defaultValue="general" className="w-full">
        <TabsList
          className="grid w-full"
          style={{ gridTemplateColumns: `repeat(${tabs.length}, minmax(0, 1fr))` }}
        >
          {tabs.map((t) => {
            const Icon = t.icon;
            return (
              <TabsTrigger key={t.value} value={t.value} className="gap-2">
                <Icon className="w-4 h-4" />
                <span className="hidden sm:inline">{t.label}</span>
              </TabsTrigger>
            );
          })}
        </TabsList>

        {/* ===================== GENERAL ===================== */}
        <TabsContent value="general" className="space-y-6">
          {/* ---- Backend connection ---- */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Server className="w-5 h-5 text-primary" />
                Backend Connection
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <Row label="API URL">
                <code className="text-xs bg-muted px-2 py-1 rounded">{API_BASE_URL}</code>
              </Row>
              <Row label="Status">
                {health.kind === 'checking' && (
                  <span className="flex items-center gap-1 text-muted-foreground">
                    <Loader2 className="w-4 h-4 animate-spin" /> Checking…
                  </span>
                )}
                {health.kind === 'ok' && (
                  <Badge variant="success" className="gap-1">
                    <CheckCircle2 className="w-3 h-3" /> Connected · {health.ms}ms
                  </Badge>
                )}
                {health.kind === 'fail' && (
                  <Badge variant="danger" className="gap-1">
                    <AlertCircle className="w-3 h-3" /> Unreachable
                  </Badge>
                )}
                {health.kind === 'idle' && <span className="text-muted-foreground">—</span>}
              </Row>
              {health.kind === 'fail' && (
                <p className="text-xs text-overdue break-words">{health.message}</p>
              )}
              <Button variant="outline" onClick={testConnection} disabled={health.kind === 'checking'} className="gap-2">
                <RefreshCw className="w-4 h-4" />
                Test connection
              </Button>
            </CardContent>
          </Card>

          {/* ---- Agent configuration (read-only) ---- */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Cpu className="w-5 h-5 text-primary" />
                Agent Configuration
                <Badge variant="secondary" className="ml-1 font-normal">read-only</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {configError && (
                <p className="text-sm text-overdue mb-3">
                  Could not load configuration: {configError}
                </p>
              )}
              {!config && !configError && (
                <div className="space-y-1">
                  {Array.from({ length: 7 }).map((_, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between gap-4 py-2 border-b border-border/50 last:border-0"
                    >
                      <Skeleton className="h-4 w-28" />
                      <Skeleton className="h-4 w-36" />
                    </div>
                  ))}
                </div>
              )}
              {config && (
                <div className="space-y-1">
                  <Row label="Environment">{config.environment}</Row>
                  <Row label="AI Provider">
                    <span className="inline-flex items-center gap-2">
                      {config.ai.active_provider}
                      {config.ai.mock_mode && <Badge variant="warning">mock mode</Badge>}
                    </span>
                  </Row>
                  <Row label="Classify model"><code className="text-xs">{config.ai.classify_model}</code></Row>
                  <Row label="Draft model"><code className="text-xs">{config.ai.draft_model}</code></Row>
                  <Row label="Outbound comms">
                    {config.comms.dryrun ? (
                      <Badge variant="warning" className="gap-1"><ShieldCheck className="w-3 h-3" /> Dry-run (safe)</Badge>
                    ) : (
                      <Badge variant="danger" className="gap-1"><ShieldAlert className="w-3 h-3" /> Live sending</Badge>
                    )}
                  </Row>
                  <Row label="Channels configured">
                    <span className="inline-flex items-center gap-2">
                      <Badge variant={config.comms.email_configured ? 'success' : 'secondary'} className="gap-1">
                        <Mail className="w-3 h-3" /> Email
                      </Badge>
                      <Badge variant={config.comms.slack_configured ? 'success' : 'secondary'} className="gap-1">
                        <MessageSquare className="w-3 h-3" /> Slack
                      </Badge>
                    </span>
                  </Row>
                  <Row label="Severity (HIGH)">
                    ≥ ${config.severity_thresholds.high_amount.toLocaleString()} or &gt;{' '}
                    {config.severity_thresholds.high_days}d
                  </Row>
                  <Row label="Priority thresholds">
                    HIGH ≥ {config.priority.high_threshold} · MED ≥ {config.priority.medium_threshold}
                  </Row>
                  <p className="text-xs text-muted-foreground pt-3">
                    Platform-wide defaults from the backend <code>.env</code> / rules engine.
                    {canManageIntegrations && ' Per-organization overrides live under the Integrations tab.'}
                  </p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* ---- Interface preferences (client-side, applied on save) ---- */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Palette className="w-5 h-5 text-primary" />
                Interface Preferences
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <label className="text-sm font-medium">Theme</label>
                  <p className="text-xs text-muted-foreground">Light, dark, or follow your OS</p>
                </div>
                <Select value={draftTheme} onValueChange={(v) => setDraftTheme(v as typeof draftTheme)}>
                  <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="light">Light</SelectItem>
                    <SelectItem value="dark">Dark</SelectItem>
                    <SelectItem value="system">System</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <label className="text-sm font-medium">Table Page Size</label>
                  <p className="text-xs text-muted-foreground">Rows per page in the Exception Queue</p>
                </div>
                <Select value={draftPageSize} onValueChange={setDraftPageSize}>
                  <SelectTrigger className="w-24"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="10">10</SelectItem>
                    <SelectItem value="25">25</SelectItem>
                    <SelectItem value="50">50</SelectItem>
                    <SelectItem value="100">100</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>

          <div className="flex items-center justify-end gap-3">
            {saved && (
              <span className="text-sm text-settled flex items-center gap-1">
                <CheckCircle2 className="w-4 h-4" /> Saved
              </span>
            )}
            <Button variant="outline" onClick={handleRestoreDefaults}>Restore defaults</Button>
            <Button onClick={handleSave} disabled={!dirty} className="gap-2">
              <Save className="w-4 h-4" />
              Save changes
            </Button>
          </div>
        </TabsContent>

        {/* ===================== INTEGRATIONS (admin) ===================== */}
        {canManageIntegrations && (
          <TabsContent value="integrations">
            <IntegrationsPanel />
          </TabsContent>
        )}

        {/* ===================== RULES (admin) ===================== */}
        {canManageIntegrations && (
          <TabsContent value="rules">
            <RulesPanel />
          </TabsContent>
        )}

        {/* ===================== BRANDING ===================== */}
        <TabsContent value="branding">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Paintbrush className="w-5 h-5 text-primary" />
                Email &amp; Slack branding
                <Badge variant="secondary" className="ml-1 font-normal">preview</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Set your signature and tone, preview exactly how an outbound message renders, and
                {canManageIntegrations
                  ? ' save it for this organization'
                  : ' (admins can save it for the organization)'}
                . Saved branding applies to every email and Slack message the agent sends.
              </p>

              <div className="grid gap-3 sm:grid-cols-2">
                <label className="space-y-1">
                  <span className="text-xs font-medium text-muted-foreground">Channel</span>
                  <Select value={brandChannel} onValueChange={(v) => setBrandChannel(v as CommChannel)}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="vendor_email">Vendor email</SelectItem>
                      <SelectItem value="internal_email">Internal email</SelectItem>
                      <SelectItem value="finance_note">Finance note</SelectItem>
                      <SelectItem value="slack">Slack</SelectItem>
                    </SelectContent>
                  </Select>
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-medium text-muted-foreground">Signature name</span>
                  <Input value={sigName} onChange={(e) => setSigName(e.target.value)} placeholder="AP Operations Team" />
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-medium text-muted-foreground">Team</span>
                  <Input value={sigTeam} onChange={(e) => setSigTeam(e.target.value)} placeholder="Accounts Payable" />
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-medium text-muted-foreground">Company</span>
                  <Input value={sigCompany} onChange={(e) => setSigCompany(e.target.value)} placeholder="Your Company" />
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-medium text-muted-foreground">Brand color</span>
                  <div className="flex items-center gap-2">
                    <input
                      type="color"
                      value={/^#[0-9a-fA-F]{6}$/.test(brandColor) ? brandColor : '#1f4e79'}
                      onChange={(e) => setBrandColor(e.target.value)}
                      className="h-9 w-10 shrink-0 cursor-pointer rounded border bg-background"
                      aria-label="Brand color"
                    />
                    <Input value={brandColor} onChange={(e) => setBrandColor(e.target.value)} placeholder="#1f4e79" />
                  </div>
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-medium text-muted-foreground">Logo URL</span>
                  <Input value={logoUrl} onChange={(e) => setLogoUrl(e.target.value)} placeholder="https://…/logo.png" />
                </label>
              </div>

              <label className="space-y-1 block">
                <span className="text-xs font-medium text-muted-foreground">Footer disclaimer</span>
                <Input
                  value={sigDisclaimer}
                  onChange={(e) => setSigDisclaimer(e.target.value)}
                  placeholder="This message is confidential and intended for the addressee only."
                />
              </label>

              <label className="space-y-1 block">
                <span className="text-xs font-medium text-muted-foreground">Sample message body</span>
                <Textarea
                  value={sampleBody}
                  onChange={(e) => setSampleBody(e.target.value)}
                  className="min-h-[120px] font-mono text-sm"
                />
              </label>

              {brandMsg && (
                <p className={`text-xs ${brandMsg.ok ? 'text-settled' : 'text-overdue'} break-words`}>
                  {brandMsg.text}
                </p>
              )}
              <div className="flex flex-wrap items-center justify-between gap-3">
                <label className="flex items-center gap-2 text-sm">
                  <Switch checked={discloseAi} onCheckedChange={setDiscloseAi} />
                  Disclose AI assistance in footer
                </label>
                <div className="flex gap-2">
                  <Button variant="outline" onClick={handleBrandPreview} disabled={previewLoading} className="gap-2">
                    {previewLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Eye className="w-4 h-4" />}
                    Preview
                  </Button>
                  {canManageIntegrations && (
                    <Button onClick={handleBrandSave} disabled={brandSaving} className="gap-2">
                      {brandSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                      Save for org
                    </Button>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ===================== ORGANIZATION (admin only) ===================== */}
        {canManageIntegrations && (
          <TabsContent value="organization">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Building2 className="w-5 h-5 text-primary" />
                Organization
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground mb-4">
                Manage members, roles, and invitations for this organization. Inviting and role
                changes are available to organization admins; members see the roster.
              </p>
              {/* Clerk's own org management panel. Hash routing keeps it self-contained
                  inside this tab (no app route changes needed). */}
              <div className="flex justify-center">
                <OrganizationProfile routing="hash" />
              </div>
            </CardContent>
          </Card>
          </TabsContent>
        )}
      </Tabs>

      <CommsPreviewDialog
        open={previewOpen}
        onOpenChange={setPreviewOpen}
        title="Branding preview"
        preview={previewData}
        loading={previewLoading}
        error={previewError}
      />
    </div>
  );
}
