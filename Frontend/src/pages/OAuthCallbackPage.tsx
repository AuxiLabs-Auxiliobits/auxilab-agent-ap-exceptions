import { useEffect, useRef, useState } from 'react';
import { useParams, useSearchParams, Link } from 'react-router-dom';
import { CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';
import { api, ApiError } from '@/lib/api';

/**
 * OAuth redirect target for Gmail/Slack connect. The provider redirects the
 * browser here with `?code&state`; we POST them to the backend to finish the
 * connection, then point the admin back to Settings. This is the URL you register
 * as the redirect URI (e.g. https://app.example.com/integrations/google/callback).
 */
export function OAuthCallbackPage() {
  const { provider } = useParams<{ provider: string }>();
  const [params] = useSearchParams();
  const [state, setState] = useState<'working' | 'ok' | 'error'>('working');
  const [detail, setDetail] = useState('');
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return; // guard against StrictMode double-invoke
    ran.current = true;
    const code = params.get('code');
    const stateParam = params.get('state');
    const oauthError = params.get('error');

    if (oauthError) {
      setState('error');
      setDetail(`Authorization was cancelled or denied (${oauthError}).`);
      return;
    }
    if ((provider !== 'google' && provider !== 'slack') || !code || !stateParam) {
      setState('error');
      setDetail('Missing or invalid OAuth response.');
      return;
    }
    void (async () => {
      try {
        const res = await api.oauthCallback(provider, code, stateParam);
        setState('ok');
        setDetail(
          provider === 'google'
            ? `Gmail connected${res.email ? ` (${res.email})` : ''}.`
            : `Slack connected${res.team ? ` (${res.team})` : ''}.`,
        );
      } catch (e) {
        setState('error');
        setDetail(e instanceof ApiError ? e.message : String(e));
      }
    })();
  }, [provider, params]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-md rounded-xl border bg-card p-8 text-center shadow-sm">
        {state === 'working' && (
          <>
            <Loader2 className="mx-auto h-8 w-8 animate-spin text-primary" />
            <p className="mt-4 text-sm text-muted-foreground">Finishing the connection…</p>
          </>
        )}
        {state === 'ok' && (
          <>
            <CheckCircle2 className="mx-auto h-8 w-8 text-settled" />
            <h1 className="mt-4 text-lg font-semibold">Connected</h1>
            <p className="mt-1 text-sm text-muted-foreground">{detail}</p>
          </>
        )}
        {state === 'error' && (
          <>
            <AlertCircle className="mx-auto h-8 w-8 text-overdue" />
            <h1 className="mt-4 text-lg font-semibold">Couldn’t connect</h1>
            <p className="mt-1 break-words text-sm text-overdue">{detail}</p>
          </>
        )}
        {state !== 'working' && (
          <Link
            to="/settings"
            className="mt-6 inline-block rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
          >
            Back to Settings
          </Link>
        )}
      </div>
    </div>
  );
}
