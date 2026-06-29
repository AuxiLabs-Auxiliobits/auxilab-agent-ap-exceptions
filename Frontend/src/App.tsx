import { lazy, Suspense, useEffect, useRef } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Show, useOrganization, useOrganizationList, OrganizationList } from '@clerk/react';
import { Skeleton } from '@/components/ui/skeleton';
import { AppShellSkeleton } from '@/components/common/AppShellSkeleton';
import { ThemeProvider } from '@/hooks/useTheme';
import { RunProvider } from '@/hooks/useRun';
import { PermissionsProvider } from '@/hooks/usePermissions';
import { PreferencesProvider, usePreferences } from '@/hooks/usePreferences';
import { TooltipProvider } from '@/components/ui/tooltip';
import { Sidebar } from '@/components/layout/Sidebar';
import { Header } from '@/components/layout/Header';
// import { AskDesk } from '@/components/assistant/AskDesk';

// Login is needed immediately, so keep it eager. Every other page is
// code-split so the initial bundle stays small (recharts/Clerk are heavy).
import { LoginPage } from '@/pages/LoginPage';
const OAuthCallbackPage = lazy(() => import('@/pages/OAuthCallbackPage').then((m) => ({ default: m.OAuthCallbackPage })));
const NewsletterPage = lazy(() => import('@/pages/NewsletterPage').then((m) => ({ default: m.NewsletterPage })));
const PrivacyPage = lazy(() => import('@/pages/LegalPage').then((m) => ({ default: m.PrivacyPage })));
const TermsPage = lazy(() => import('@/pages/LegalPage').then((m) => ({ default: m.TermsPage })));
const DashboardPage = lazy(() => import('@/pages/DashboardPage').then((m) => ({ default: m.DashboardPage })));
const QueuePage = lazy(() => import('@/pages/QueuePage').then((m) => ({ default: m.QueuePage })));
const ClassificationPage = lazy(() => import('@/pages/ClassificationPage').then((m) => ({ default: m.ClassificationPage })));
const ResolutionPage = lazy(() => import('@/pages/ResolutionPage').then((m) => ({ default: m.ResolutionPage })));
const CommunicationsPage = lazy(() => import('@/pages/CommunicationsPage').then((m) => ({ default: m.CommunicationsPage })));
const RunHistoryPage = lazy(() => import('@/pages/RunHistoryPage').then((m) => ({ default: m.RunHistoryPage })));
const SlaPage = lazy(() => import('@/pages/SlaPage').then((m) => ({ default: m.SlaPage })));
const DuplicatesPage = lazy(() => import('@/pages/DuplicatesPage').then((m) => ({ default: m.DuplicatesPage })));
const CasesPage = lazy(() => import('@/pages/CasesPage').then((m) => ({ default: m.CasesPage })));
const VendorsPage = lazy(() => import('@/pages/VendorsPage').then((m) => ({ default: m.VendorsPage })));
const AnalyticsPage = lazy(() => import('@/pages/AnalyticsPage').then((m) => ({ default: m.AnalyticsPage })));
const SettingsPage = lazy(() => import('@/pages/SettingsPage').then((m) => ({ default: m.SettingsPage })));

// Public documentation site (no login). Code-split so it never weighs down the
// authenticated console bundle.
const DocsLayout = lazy(() => import('@/docs/DocsLayout').then((m) => ({ default: m.DocsLayout })));
const DocsHome = lazy(() => import('@/docs/DocsHome').then((m) => ({ default: m.DocsHome })));
const DocsPage = lazy(() => import('@/docs/DocsPage').then((m) => ({ default: m.DocsPage })));

function PageFallback() {
  return (
    <div className="space-y-6 py-2" aria-busy="true">
      <Skeleton className="h-8 w-56" />
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full rounded-lg" />
        ))}
      </div>
      <Skeleton className="h-64 w-full rounded-lg" />
    </div>
  );
}

function DefaultRedirect() {
  const { preferences } = usePreferences();
  return <Navigate to={preferences.defaultView} replace />;
}

function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center h-full py-24 text-center gap-3">
      <p className="text-5xl font-semibold text-muted-foreground">404</p>
      <p className="text-lg">This page doesn’t exist.</p>
      <a href="/" className="text-primary underline underline-offset-4">
        Go back to the dashboard
      </a>
    </div>
  );
}

/**
 * Tenant boundary: the console is scoped to a Clerk organization (its id is the
 * backend `tenant_id`). A signed-in user with no active organization is sent to
 * an org picker rather than into the app, so a personal (no-org) context — which
 * the backend would treat as a private per-user tenant — can never silently
 * become the working context.
 */
function RequireActiveOrg({ children }: { children: React.ReactNode }) {
  const { isLoaded: orgLoaded, organization } = useOrganization();
  const { isLoaded: listLoaded, setActive, userMemberships } = useOrganizationList({
    userMemberships: true,
  });

  // The user's org memberships (first page is enough — we only need to know
  // whether there's exactly one to auto-activate).
  const memberships = userMemberships?.data ?? [];
  const membershipsLoading = userMemberships?.isLoading ?? true;
  const soleOrgId =
    !organization && memberships.length === 1 ? memberships[0].organization.id : null;

  // A member of exactly one organization shouldn't see a picker — silently
  // activate it and drop straight into the dashboard. (Clerk does NOT
  // auto-activate a single membership; without this the user is stuck on the
  // org selector even though there's only one choice.)
  useEffect(() => {
    if (soleOrgId && setActive) void setActive({ organization: soleOrgId });
  }, [soleOrgId, setActive]);

  if (!orgLoaded || !listLoaded || membershipsLoading) return <AppShellSkeleton />;
  if (organization) return <>{children}</>;
  if (soleOrgId) return <AppShellSkeleton />; // activating the sole org — brief loader
  // 0 memberships (accept an invite / ask an admin) or 2+ (genuinely choose one).
  return <OrgSelectionScreen />;
}

function OrgSelectionScreen() {
  return (
    <div className="flex h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-md">
        <div className="mb-6 text-center">
          <h1 className="text-xl font-semibold">Select your organization</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            The clearing desk is scoped to an organization. Select one below — or accept a
            pending invitation — to continue. Each organization’s runs, drafts, and audit
            trail stay fully isolated.
          </p>
        </div>
        {/* Invitation-only model: organizations are provisioned by the platform
            administrator and members join by invitation, so self-service "create
            organization" is disabled at the Clerk instance level (Organizations
            Settings → "Allow user-created Organizations" off). With that off, Clerk
            hides the create button here automatically. */}
        <OrganizationList
          hidePersonal
          afterSelectOrganizationUrl="/dashboard"
          afterCreateOrganizationUrl="/dashboard"
        />
        <p className="mt-6 text-center text-xs text-muted-foreground">
          Don’t see your organization? Ask your administrator to invite you — once you
          accept, you’ll land here automatically.
        </p>
      </div>
    </div>
  );
}

/**
 * Hard-reload when the active organization (tenant) changes, so every provider
 * re-fetches with the new org's token and no stale tenant data lingers. Mounted
 * once for the whole session; the first observed org is recorded without a reload.
 */
function OrgContextManager() {
  const { isLoaded, organization } = useOrganization();
  const prevOrgId = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    if (!isLoaded) return;
    const id = organization?.id ?? null;
    if (prevOrgId.current === undefined) {
      prevOrgId.current = id; // record the initial value; never reload on mount
      return;
    }
    if (prevOrgId.current !== id) {
      window.location.reload();
      return;
    }
    prevOrgId.current = id;
  }, [isLoaded, organization?.id]);
  return null;
}

function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      {/* Route guard: signed-out users are bounced to the login screen. */}
      <Show when="signed-out">
        <Navigate to="/login" replace />
      </Show>
      <Show when="signed-in">
        <RequireActiveOrg>
          <div className="flex h-screen overflow-hidden bg-background">
            <Sidebar />
            <div className="flex-1 flex flex-col overflow-hidden">
              <Header />
              <main className="flex-1 overflow-auto p-6">
                <Suspense fallback={<PageFallback />}>{children}</Suspense>
              </main>
            </div>
            {/* <AskDesk /> */}
          </div>
        </RequireActiveOrg>
      </Show>
    </>
  );
}

function App() {
  return (
    <ThemeProvider defaultTheme="system" storageKey="ap-theme">
      <PreferencesProvider>
        <PermissionsProvider>
        <RunProvider>
          <TooltipProvider>
            <Router>
          <OrgContextManager />
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            {/* OAuth redirect target for Gmail/Slack connect (Settings → Integrations). */}
            <Route
              path="/integrations/:provider/callback"
              element={
                <Suspense fallback={<PageFallback />}>
                  <OAuthCallbackPage />
                </Suspense>
              }
            />
            {/* Platform-operator newsletter composer (token-gated, not in app nav). */}
            <Route
              path="/newsletter"
              element={
                <Suspense fallback={<PageFallback />}>
                  <NewsletterPage />
                </Suspense>
              }
            />
            <Route
              path="/privacy"
              element={
                <Suspense fallback={<PageFallback />}>
                  <PrivacyPage />
                </Suspense>
              }
            />
            <Route
              path="/terms"
              element={
                <Suspense fallback={<PageFallback />}>
                  <TermsPage />
                </Suspense>
              }
            />
            {/* Public documentation — accessible without login. */}
            <Route
              path="/docs"
              element={
                <Suspense fallback={<PageFallback />}>
                  <DocsLayout />
                </Suspense>
              }
            >
              <Route
                index
                element={
                  <Suspense fallback={<PageFallback />}>
                    <DocsHome />
                  </Suspense>
                }
              />
              <Route
                path=":slug"
                element={
                  <Suspense fallback={<PageFallback />}>
                    <DocsPage />
                  </Suspense>
                }
              />
            </Route>
            <Route
              path="/dashboard"
              element={
                <AppLayout>
                  <DashboardPage />
                </AppLayout>
              }
            />
            <Route
              path="/queue"
              element={
                <AppLayout>
                  <QueuePage />
                </AppLayout>
              }
            />
            <Route
              path="/classification"
              element={
                <AppLayout>
                  <ClassificationPage />
                </AppLayout>
              }
            />
            <Route
              path="/resolution"
              element={
                <AppLayout>
                  <ResolutionPage />
                </AppLayout>
              }
            />
            <Route
              path="/communications"
              element={
                <AppLayout>
                  <CommunicationsPage />
                </AppLayout>
              }
            />
            <Route
              path="/cases"
              element={
                <AppLayout>
                  <CasesPage />
                </AppLayout>
              }
            />
            {/* Priority Queue merged into Exceptions — redirect to the board view. */}
            <Route path="/priority" element={<Navigate to="/queue?view=priority" replace />} />
            <Route
              path="/history"
              element={
                <AppLayout>
                  <RunHistoryPage />
                </AppLayout>
              }
            />
            <Route
              path="/sla"
              element={
                <AppLayout>
                  <SlaPage />
                </AppLayout>
              }
            />
            <Route
              path="/vendors"
              element={
                <AppLayout>
                  <VendorsPage />
                </AppLayout>
              }
            />
            <Route
              path="/duplicates"
              element={
                <AppLayout>
                  <DuplicatesPage />
                </AppLayout>
              }
            />
            <Route
              path="/analytics"
              element={
                <AppLayout>
                  <AnalyticsPage />
                </AppLayout>
              }
            />
            <Route
              path="/settings"
              element={
                <AppLayout>
                  <SettingsPage />
                </AppLayout>
              }
            />
            <Route path="/" element={<DefaultRedirect />} />
            {/* Catch-all: unmapped paths render an in-app 404 (inside the
                authenticated shell) instead of a blank screen. */}
            <Route
              path="*"
              element={
                <AppLayout>
                  <NotFoundPage />
                </AppLayout>
              }
            />
          </Routes>
            </Router>
          </TooltipProvider>
        </RunProvider>
        </PermissionsProvider>
      </PreferencesProvider>
    </ThemeProvider>
  );
}

export default App;
