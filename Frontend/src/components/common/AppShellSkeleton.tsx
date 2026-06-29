import { Skeleton } from '@/components/ui/skeleton';

// One width per primary nav row (mirrors the 12 items in Sidebar's `navigation`),
// varied to look like real labels rather than identical bars.
const NAV_ROW_WIDTHS = [
  'w-24', 'w-24', 'w-24', 'w-24', 'w-28', 'w-32',
  'w-32', 'w-32', 'w-16', 'w-28', 'w-20', 'w-20',
];

/**
 * Full app-shell skeleton shown on a cold reload — BEFORE the authenticated
 * layout (sidebar + header) mounts, i.e. while Clerk resolves the active
 * organization. It mirrors AppLayout's structure (280px sidebar with a row per
 * nav item, a top header bar, the content area) so the user sees the whole shell
 * as a skeleton instead of a bare floating block, and nothing jumps when the
 * real chrome appears.
 */
export function AppShellSkeleton() {
  return (
    <div
      className="flex h-screen overflow-hidden bg-background"
      aria-busy="true"
      aria-label="Loading"
    >
      {/* ---- Sidebar ---- */}
      <aside className="flex w-[280px] shrink-0 flex-col border-r border-border bg-card">
        {/* Brand header (matches Sidebar's h-16 px-4 brand block) */}
        <div className="flex h-16 items-center gap-2.5 border-b border-border px-4">
          <Skeleton className="h-9 w-9 shrink-0 rounded-lg" />
          <div className="space-y-1.5">
            <Skeleton className="h-3.5 w-24" />
            <Skeleton className="h-2.5 w-20" />
          </div>
        </div>

        {/* Nav rows — one skeleton row per nav item (icon + name) */}
        <nav className="flex-1 space-y-1 p-3">
          {NAV_ROW_WIDTHS.map((w, i) => (
            <div key={i} className="flex items-center gap-3 px-3 py-2.5">
              <Skeleton className="h-[18px] w-[18px] shrink-0 rounded" />
              <Skeleton className={`h-4 ${w}`} />
            </div>
          ))}
        </nav>

        {/* Engine-status box (matches Sidebar's footer card) */}
        <div className="border-t border-border p-3">
          <div className="flex items-center gap-3 rounded-md border border-border bg-muted/50 px-3 py-2.5">
            <Skeleton className="h-2.5 w-2.5 shrink-0 rounded-full" />
            <div className="flex-1 space-y-1.5">
              <Skeleton className="h-3 w-28" />
              <Skeleton className="h-2.5 w-20" />
            </div>
          </div>
        </div>
      </aside>

      {/* ---- Main column ---- */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top header bar (matches Header's h-16, right-aligned controls) */}
        <header className="flex h-16 items-center justify-end gap-3 border-b bg-card/50 px-6">
          <Skeleton className="h-8 w-28 rounded-md" />
          <Skeleton className="h-8 w-8 rounded-md" />
          <Skeleton className="h-8 w-8 rounded-md" />
          <Skeleton className="h-8 w-8 rounded-full" />
        </header>

        {/* Content (same shape as PageFallback) */}
        <main className="flex-1 overflow-auto p-6">
          <div className="space-y-6">
            <Skeleton className="h-8 w-56" />
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-24 w-full rounded-lg" />
              ))}
            </div>
            <Skeleton className="h-64 w-full rounded-lg" />
          </div>
        </main>
      </div>
    </div>
  );
}
