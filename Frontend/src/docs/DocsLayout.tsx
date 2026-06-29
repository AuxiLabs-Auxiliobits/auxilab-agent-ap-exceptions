import { useState } from 'react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { Menu, X, Bell, BookOpen, Search, ArrowUpRight } from 'lucide-react';
import { ThemeToggle } from '@/components/layout/ThemeToggle';
import { cn } from '@/lib/utils';
import { DOC_GROUPS } from './manifest';
import { DocsSearchProvider, SearchTrigger, useDocsSearch } from './DocsSearch';

export function DocsLayout() {
  return (
    <DocsSearchProvider>
      <DocsShell />
    </DocsSearchProvider>
  );
}

function DocsShell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { pathname } = useLocation();
  const search = useDocsSearch();

  // Right-nav active state. "Documentation" is the default highlight for any
  // docs page that isn't one of the dedicated destinations.
  const onApi = pathname === '/docs/api-reference';
  const onWhatsNew = pathname === '/docs/release-notes';
  const onDocs = !onApi && !onWhatsNew;

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* ---- Top bar ---- */}
      <header className="sticky top-0 z-40 border-b border-border bg-background/90 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-[1400px] items-center gap-4 px-4 sm:px-6">
          <button
            className="grid h-9 w-9 place-items-center rounded-md border border-border lg:hidden"
            onClick={() => setMobileOpen((v) => !v)}
            aria-label="Toggle navigation"
          >
            {mobileOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
          </button>

          <Link to="/docs" className="flex shrink-0 items-center gap-2.5">
            <Logomark />
            <span className="hidden text-[17px] font-semibold tracking-tight sm:block">
              LedgerClear <span className="text-muted-foreground">Docs</span>
            </span>
          </Link>

          {/* Centered search */}
          <div className="hidden flex-1 justify-center px-4 md:flex">
            <SearchTrigger className="w-full max-w-xl" />
          </div>

          {/* Right nav */}
          <nav className="ml-auto flex items-center gap-1" aria-label="Primary">
            <button
              onClick={search.open}
              className="grid h-9 w-9 place-items-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground md:hidden"
              aria-label="Search"
            >
              <Search className="h-4 w-4" />
            </button>
            <TopLink to="/docs/release-notes" icon={Bell} label="What's New" active={onWhatsNew} />
            <TopLink to="/docs" icon={BookOpen} label="Documentation" active={onDocs} />
            <a
              href="/login"
              className="hidden items-center gap-1 rounded-full px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground xl:inline-flex"
            >
              Console <ArrowUpRight className="h-3.5 w-3.5" />
            </a>
            <ThemeToggle />
          </nav>
        </div>
      </header>

      <div className="mx-auto flex max-w-[1400px]">
        {/* ---- Sidebar ---- */}
        <aside
          className={cn(
            'fixed inset-y-0 left-0 z-30 w-72 shrink-0 overflow-y-auto border-r border-border bg-background px-3 pb-12 pt-20 transition-transform lg:sticky lg:top-16 lg:z-0 lg:h-[calc(100vh-4rem)] lg:translate-x-0 lg:pt-6',
            mobileOpen ? 'translate-x-0' : '-translate-x-full',
          )}
        >
          <div className="mb-4 md:hidden">
            <SearchTrigger className="w-full" />
          </div>
          <nav className="space-y-7" aria-label="Documentation">
            {DOC_GROUPS.map((g) => (
              <div key={g.title}>
                <p className="mb-2 px-3 font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                  {g.title}
                </p>
                <ul className="space-y-0.5">
                  {g.pages.map((p) => {
                    const Icon = p.icon;
                    return (
                      <li key={p.slug}>
                        <NavLink
                          to={`/docs/${p.slug}`}
                          onClick={() => setMobileOpen(false)}
                          className={({ isActive }) =>
                            cn(
                              'flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors',
                              isActive
                                ? 'bg-primary/10 font-medium text-primary'
                                : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                            )
                          }
                        >
                          {({ isActive }) => (
                            <>
                              <Icon className={cn('h-4 w-4 shrink-0', isActive ? 'text-primary' : 'text-muted-foreground')} />
                              {p.title}
                            </>
                          )}
                        </NavLink>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </nav>
        </aside>

        {mobileOpen && (
          <button
            className="fixed inset-0 z-20 bg-foreground/20 lg:hidden"
            aria-label="Close navigation"
            onClick={() => setMobileOpen(false)}
          />
        )}

        {/* ---- Content ---- */}
        <main key={pathname} className="min-w-0 flex-1 px-4 py-8 sm:px-8 lg:px-12">
          <div className="mx-auto max-w-3xl">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}

function TopLink({
  to,
  icon: Icon,
  label,
  active,
}: {
  to: string;
  icon: typeof Bell;
  label: string;
  active: boolean;
}) {
  return (
    <Link
      to={to}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'hidden items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm font-medium transition-colors lg:inline-flex',
        active
          ? 'border-primary bg-primary/10 text-primary shadow-sm'
          : 'border-transparent text-muted-foreground hover:border-primary/40 hover:text-foreground',
      )}
    >
      <Icon className="h-4 w-4" />
      {label}
    </Link>
  );
}

// Same brand mark as the homepage header, so the docs read as one product.
function Logomark() {
  return (
    <span className="grid h-9 w-9 place-items-center rounded-lg bg-primary text-primary-foreground shadow-sm">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden role="img">
        <line x1="5.5" y1="7" x2="15.5" y2="7" stroke="currentColor" strokeOpacity="0.6" strokeWidth="2" strokeLinecap="round" />
        <line x1="5.5" y1="11" x2="12.5" y2="11" stroke="currentColor" strokeOpacity="0.6" strokeWidth="2" strokeLinecap="round" />
        <path d="M5.5 16.5 L9.5 20 L19 9.5" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}
