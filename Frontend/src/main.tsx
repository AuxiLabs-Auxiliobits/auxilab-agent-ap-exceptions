import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ClerkProvider } from '@clerk/react'
import './index.css'
import App from './App.tsx'
import { ErrorBoundary } from '@/components/common/ErrorBoundary'

// @clerk/react v6 requires the publishable key as a prop (the env-only form
// doesn't satisfy its types). Read it from the Vite env var.
const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined

const root = createRoot(document.getElementById('root')!)

// Clerk publishable keys always start with `pk_test_` or `pk_live_`. If the
// key is missing or still the placeholder, render a clear setup message
// instead of letting Clerk fail with a blank screen.
if (!PUBLISHABLE_KEY || !PUBLISHABLE_KEY.startsWith('pk_')) {
  root.render(
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: 'system-ui, sans-serif',
        background: '#0a0a0a',
        color: '#e2e8f0',
        padding: 24,
      }}
    >
      <div style={{ maxWidth: 520, lineHeight: 1.6 }}>
        <h1 style={{ fontSize: 22, marginBottom: 12 }}>🔑 Clerk key not configured</h1>
        <p style={{ color: '#94a3b8' }}>
          The app needs a real Clerk <strong>publishable key</strong> to show the
          sign-in form.
        </p>
        <ol style={{ color: '#94a3b8', paddingLeft: 20 }}>
          <li>Clerk Dashboard → <strong>API keys</strong> → React → copy the key (starts with <code>pk_test_</code>).</li>
          <li>Paste it into <code>.env.local</code>:<br />
            <code style={{ color: '#38bdf8' }}>VITE_CLERK_PUBLISHABLE_KEY=pk_test_…</code>
          </li>
          <li><strong>Restart</strong> the dev server (<code>npm run dev</code>) — Vite only reads env vars at startup.</li>
        </ol>
        <p style={{ color: '#64748b', fontSize: 13, marginTop: 16 }}>
          Current value: <code>{PUBLISHABLE_KEY || '(unset)'}</code>
        </p>
      </div>
    </div>,
  )
} else {
  root.render(
    <StrictMode>
      <ErrorBoundary>
        <ClerkProvider publishableKey={PUBLISHABLE_KEY} afterSignOutUrl="/login">
          <App />
        </ClerkProvider>
      </ErrorBoundary>
    </StrictMode>,
  )
}
