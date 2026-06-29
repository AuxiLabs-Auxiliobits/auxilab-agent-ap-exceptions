import { useEffect, useState } from 'react';
import {
  ScrollText,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Save,
  RotateCcw,
  ShieldCheck,
  FlaskConical,
  ArrowRight,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { useRun } from '@/hooks/useRun';
import { api, ApiError, type RuleOverridesReport, type RuleSimulation } from '@/lib/api';
import { resolutionPathLabel as pathLabel } from '@/lib/resolutionLabels';

/**
 * Per-org rulebook editor (admin-only). Shows the org's effective resolution
 * policy as JSON; the admin can validate, save (overriding the platform
 * default), or revert. The backend re-validates on save and enforces the
 * mandatory catch-all rule, so an unsafe policy can never be stored. Global
 * guardrails (materiality ceiling, confidence floor) still apply on top.
 */
export function RulesPanel() {
  const { runId } = useRun();
  const [text, setText] = useState('');
  const [isCustom, setIsCustom] = useState(false);
  const [defaultPolicy, setDefaultPolicy] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<'save' | 'validate' | 'revert' | 'simulate' | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [overrides, setOverrides] = useState<RuleOverridesReport | null>(null);
  const [sim, setSim] = useState<RuleSimulation | null>(null);

  const load = async () => {
    try {
      const r = await api.getRules();
      setText(JSON.stringify(r.policy, null, 2));
      setIsCustom(r.is_custom);
      setDefaultPolicy(r.default_policy);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // The override report is a best-effort tuning aid — failure shouldn't block the editor.
    void api.getRuleOverrides().then(setOverrides).catch(() => {});
  }, []);

  /** Parse the editor text, surfacing JSON syntax errors as a friendly message. */
  const parsed = (): unknown => {
    try {
      return JSON.parse(text);
    } catch (e) {
      throw new Error(`Not valid JSON: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const validate = async () => {
    setBusy('validate');
    setMsg(null);
    try {
      const r = await api.validateRules(parsed());
      setMsg(
        r.ok
          ? { ok: true, text: `Valid — version "${r.version}", ${r.rules} rules.` }
          : { ok: false, text: r.error ?? 'Invalid policy.' },
      );
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  };

  const simulate = async () => {
    if (!runId) return;
    setBusy('simulate');
    setMsg(null);
    setSim(null);
    try {
      const r = await api.simulateRules(runId, parsed());
      setSim(r);
      if (r.changed_count === 0) {
        setMsg({ ok: true, text: `No change — all ${r.total} invoice(s) route the same under this policy.` });
      }
    } catch (e) {
      setMsg({ ok: false, text: e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  };

  const save = async () => {
    setBusy('save');
    setMsg(null);
    try {
      const r = await api.putRules(parsed());
      setMsg({
        ok: true,
        text: `Saved — this org now uses rulebook version "${r.version}". It applies to the next run; existing runs keep their routing. Use “Simulate on current run” to preview the impact.`,
      });
      await load();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof ApiError ? e.message : e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  };

  const revert = async () => {
    if (!window.confirm('Revert to the platform default rulebook? Your custom rules will be removed.'))
      return;
    setBusy('revert');
    setMsg(null);
    try {
      await api.deleteRules();
      setMsg({ ok: true, text: 'Reverted to the platform default rulebook.' });
      await load();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof ApiError ? e.message : String(e) });
    } finally {
      setBusy(null);
    }
  };

  const loadDefaultIntoEditor = () => {
    if (defaultPolicy != null) setText(JSON.stringify(defaultPolicy, null, 2));
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ScrollText className="w-5 h-5 text-primary" />
          Resolution rulebook
          <Badge variant="secondary" className="ml-1 font-normal">admin</Badge>
          {!loading &&
            (isCustom ? (
              <Badge variant="success" className="gap-1">
                <CheckCircle2 className="w-3 h-3" /> Custom
              </Badge>
            ) : (
              <Badge variant="secondary">Platform default</Badge>
            ))}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">
          This organization&apos;s routing rules (first-match-wins; a catch-all rule is required).
          Tune your own thresholds — saving validates the policy and the change applies to the next
          run. Global guardrails (the materiality ceiling and confidence floor) still apply on top
          and can&apos;t be disabled here.
        </p>

        {loading && (
          <div className="space-y-3" aria-busy="true">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-44 w-full" />
          </div>
        )}
        {error && <p className="text-sm text-overdue">Could not load rulebook: {error}</p>}

        {!loading && !error && (
          <>
            <Textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              spellCheck={false}
              className="min-h-[360px] font-mono text-xs"
              aria-label="Rulebook JSON"
            />

            {msg && (
              <p
                className={`text-xs ${msg.ok ? 'text-settled' : 'text-overdue'} whitespace-pre-wrap break-words`}
              >
                {msg.text}
              </p>
            )}

            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" variant="outline" onClick={validate} disabled={busy !== null} className="gap-2">
                {busy === 'validate' ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
                Validate
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={simulate}
                disabled={busy !== null || !runId}
                title={runId ? 'Preview how the current run would re-route under this policy' : 'No active run to simulate against — open or upload a run first'}
                className="gap-2"
              >
                {busy === 'simulate' ? <Loader2 className="w-4 h-4 animate-spin" /> : <FlaskConical className="w-4 h-4" />}
                Simulate on current run
              </Button>
              <Button size="sm" onClick={save} disabled={busy !== null} className="gap-2">
                {busy === 'save' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                Save for org
              </Button>
              <Button size="sm" variant="outline" onClick={loadDefaultIntoEditor} disabled={busy !== null} className="gap-2">
                Load default into editor
              </Button>
              {isCustom && (
                <Button size="sm" variant="outline" onClick={revert} disabled={busy !== null} className="gap-2 text-overdue">
                  {busy === 'revert' ? <Loader2 className="w-4 h-4 animate-spin" /> : <RotateCcw className="w-4 h-4" />}
                  Revert to default
                </Button>
              )}
            </div>

            <div className="flex items-start gap-2 rounded-lg border border-pending/25 bg-pending/10 p-3 text-xs text-pending">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>
                The last rule must be a catch-all (empty <code>when</code>). Save is rejected if the
                policy is malformed or missing it — your current rulebook stays unchanged.
              </span>
            </div>

            {sim && (
              <div className="rounded-lg border p-3 space-y-3">
                <div className="flex items-center gap-2">
                  <FlaskConical className="h-4 w-4 text-primary" />
                  <p className="text-sm font-medium">
                    Impact on run {sim.run_id.replace(/^run_/, '').slice(0, 8)}:{' '}
                    <span className={sim.changed_count > 0 ? 'text-primary' : 'text-settled'}>
                      {sim.changed_count}
                    </span>{' '}
                    of {sim.total} invoice{sim.total === 1 ? '' : 's'} would re-route
                  </p>
                </div>

                {/* Distribution diff: current → simulated per path. */}
                <div className="space-y-1">
                  {Array.from(
                    new Set([
                      ...Object.keys(sim.current_distribution),
                      ...Object.keys(sim.simulated_distribution),
                    ]),
                  )
                    .sort()
                    .map((p) => {
                      const cur = sim.current_distribution[p] ?? 0;
                      const next = sim.simulated_distribution[p] ?? 0;
                      const delta = next - cur;
                      return (
                        <div key={p} className="flex items-center justify-between gap-2 text-xs">
                          <span>{pathLabel(p)}</span>
                          <span className="flex items-center gap-1.5 tabular-nums">
                            <span className="text-muted-foreground">{cur}</span>
                            <ArrowRight className="h-3 w-3 text-muted-foreground" />
                            <span className="font-medium">{next}</span>
                            {delta !== 0 && (
                              <span className={delta > 0 ? 'text-settled' : 'text-overdue'}>
                                ({delta > 0 ? '+' : ''}
                                {delta})
                              </span>
                            )}
                          </span>
                        </div>
                      );
                    })}
                </div>

                {/* The re-routed invoices. */}
                {sim.changes.length > 0 && (
                  <div className="space-y-1 border-t pt-2">
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      Re-routed invoices
                    </p>
                    {sim.changes.slice(0, 20).map((ch) => (
                      <div key={ch.invoice_id} className="flex flex-wrap items-center gap-x-2 text-xs">
                        <span className="font-mono">{ch.invoice_id}</span>
                        <span className="truncate text-muted-foreground">{ch.vendor_name}</span>
                        <span className="ml-auto flex items-center gap-1.5">
                          <span className="text-muted-foreground">{pathLabel(ch.from)}</span>
                          <ArrowRight className="h-3 w-3" />
                          <span className="font-medium">{pathLabel(ch.to)}</span>
                        </span>
                      </div>
                    ))}
                    {sim.changes.length > 20 && (
                      <p className="text-xs text-muted-foreground">+{sim.changes.length - 20} more…</p>
                    )}
                  </div>
                )}
                <p className="text-xs text-muted-foreground">
                  Preview only — nothing is saved. Click “Save for org” to apply this rulebook to future runs.
                </p>
              </div>
            )}

            {overrides && overrides.rules.length > 0 && (
              <div className="rounded-lg border p-3 space-y-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Most-overridden rules
                  <span className="ml-2 font-normal normal-case text-muted-foreground/80">
                    {overrides.total_overrides} override{overrides.total_overrides === 1 ? '' : 's'} across{' '}
                    {overrides.runs_scanned} run{overrides.runs_scanned === 1 ? '' : 's'}
                  </span>
                </p>
                <p className="text-xs text-muted-foreground">
                  Rules your team most often corrects by hand — likely candidates to retune above.
                </p>
                <ul className="space-y-1">
                  {overrides.rules.slice(0, 8).map((r) => {
                    const top = Object.entries(r.to_paths).sort((a, b) => b[1] - a[1])[0];
                    return (
                      <li key={r.rule_id} className="flex items-center justify-between gap-2 text-xs">
                        <span className="font-mono truncate">{r.rule_id}</span>
                        <span className="shrink-0 text-muted-foreground">
                          {r.count}× → mostly <span className="font-medium text-foreground">{top?.[0]}</span>
                        </span>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
