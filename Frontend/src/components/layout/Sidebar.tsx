import { useState } from 'react';
import { useLocation, Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard,
  FileText,
  Sparkles,
  GitBranch,
  MessageSquare,
  BarChart3,
  Settings,
  ChevronLeft,
  ChevronRight,
  History,
  Building2,
  Timer,
  CopyCheck,
  ClipboardCheck,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { useRun } from '@/hooks/useRun';
import { useSla } from '@/hooks/useSla';

const navigation = [
  { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
  // One screen, two lenses (Table + Priority board) — see QueuePage.
  { name: 'Exceptions', href: '/queue', icon: FileText },
  { name: 'Run History', href: '/history', icon: History },
  { name: 'SLA Tracker', href: '/sla', icon: Timer },
  { name: 'Classification', href: '/classification', icon: Sparkles },
  { name: 'Resolution Paths', href: '/resolution', icon: GitBranch },
  { name: 'Communications', href: '/communications', icon: MessageSquare },
  { name: 'Resolution Tracker', href: '/cases', icon: ClipboardCheck },
  { name: 'Vendors', href: '/vendors', icon: Building2 },
  { name: 'Duplicate Check', href: '/duplicates', icon: CopyCheck },
  { name: 'Analytics', href: '/analytics', icon: BarChart3 },
  { name: 'Settings', href: '/settings', icon: Settings },
];

/**
 * LedgerClear logomark: a filled corporate-blue chip with white ledger rules
 * whose bottom line resolves into a clearing check — "ledger, cleared".
 * Token-driven (bg-primary + currentColor) so it reads in light and dark.
 */
function Logomark() {
  return (
    <span className="shrink-0 grid place-items-center w-9 h-9 rounded-lg bg-primary text-primary-foreground shadow-sm">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden role="img">
        <line x1="5.5" y1="7" x2="15.5" y2="7" stroke="currentColor" strokeOpacity="0.6" strokeWidth="2" strokeLinecap="round" />
        <line x1="5.5" y1="11" x2="12.5" y2="11" stroke="currentColor" strokeOpacity="0.6" strokeWidth="2" strokeLinecap="round" />
        <path d="M5.5 16.5 L9.5 20 L19 9.5" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();
  const { status, isProcessing, rowsAccepted, currentNode } = useRun();
  const { atRisk, breached } = useSla();

  const engineLabel = isProcessing
    ? currentNode
      ? `Processing · ${currentNode}`
      : 'Processing…'
    : status === 'AWAITING_REVIEW'
      ? 'Awaiting review'
      : status === 'COMPLETED'
        ? 'Run complete'
        : status === 'FAILED'
          ? 'Run failed'
          : 'Idle — no active run';

  const engineSub = status ? `${rowsAccepted} rows in run` : 'Upload a queue to start';
  // Status lamp uses the exception scale (theme-aware tokens): settled = clear,
  // pending = processing/awaiting, overdue = failed.
  const dotClass = isProcessing
    ? 'bg-pending animate-pulse'
    : status === 'FAILED'
      ? 'bg-overdue'
      : status
        ? 'bg-settled'
        : 'bg-muted-foreground/40';

  return (
    <motion.aside
      initial={false}
      animate={{ width: collapsed ? 80 : 280 }}
      transition={{ duration: 0.3, ease: 'easeInOut' }}
      className="relative flex flex-col bg-card text-card-foreground border-r border-border"
    >
      <div className="flex flex-col h-full">
        <div
          className={cn(
            'border-b border-border',
            collapsed
              ? 'flex flex-col items-center gap-2 py-3'
              : 'flex items-center justify-between h-16 px-4',
          )}
        >
          <div className="flex items-center gap-2.5 min-w-0">
            <Logomark />
            <AnimatePresence mode="wait">
              {!collapsed && (
                <motion.div
                  initial={{ opacity: 0, x: -12 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -12 }}
                  className="min-w-0"
                >
                  <h1 className="font-display font-semibold text-[15px] leading-tight text-foreground">
                    LedgerClear
                  </h1>
                  <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                    AP Reconciliation
                  </p>
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          <Button
            variant="ghost"
            size="icon"
            onClick={() => setCollapsed(!collapsed)}
            className="h-8 w-8 shrink-0 text-muted-foreground hover:text-foreground hover:bg-accent"
            aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}
          >
            {collapsed ? (
              <ChevronRight className="h-4 w-4" />
            ) : (
              <ChevronLeft className="h-4 w-4" />
            )}
          </Button>
        </div>

        <nav className="flex-1 p-3 space-y-1" aria-label="Primary">
          {navigation.map((item) => {
            const isActive = location.pathname === item.href;
            return (
              <Link key={item.name} to={item.href} aria-current={isActive ? 'page' : undefined}>
                <motion.div
                  whileHover={{ x: 3 }}
                  whileTap={{ scale: 0.98 }}
                  className={cn(
                    'relative flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors duration-200',
                    isActive
                      ? 'bg-primary/10 text-primary'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                  )}
                >
                  {/* Blue ledger-margin marker on the active row. */}
                  {isActive && (
                    <span className="absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-full bg-primary" />
                  )}
                  <item.icon
                    className={cn(
                      'h-[18px] w-[18px] shrink-0',
                      isActive && 'text-primary',
                    )}
                  />
                  {/* Collapsed: a small at-risk dot on the SLA icon. */}
                  {collapsed && item.href === '/sla' && atRisk > 0 && (
                    <span
                      className={cn(
                        'absolute right-1.5 top-1.5 h-2 w-2 rounded-full',
                        breached > 0 ? 'bg-overdue' : 'bg-pending',
                      )}
                      aria-hidden
                    />
                  )}
                  <AnimatePresence mode="wait">
                    {!collapsed && (
                      <motion.span
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.15 }}
                      >
                        {item.name}
                      </motion.span>
                    )}
                  </AnimatePresence>
                  {/* Expanded: an at-risk count badge on the SLA row. */}
                  {!collapsed && item.href === '/sla' && atRisk > 0 && (
                    <span
                      title={`${atRisk} at risk${breached > 0 ? ` · ${breached} breached` : ''}`}
                      className={cn(
                        'ml-auto inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[11px] font-semibold',
                        breached > 0 ? 'bg-overdue/15 text-overdue' : 'bg-pending/15 text-pending',
                      )}
                    >
                      {atRisk}
                    </span>
                  )}
                </motion.div>
              </Link>
            );
          })}
        </nav>

        <div className="p-3 border-t border-border">
          <div className="flex items-center gap-3 px-3 py-2.5 rounded-md bg-muted/50 border border-border">
            <span className="relative flex h-2.5 w-2.5 shrink-0" aria-hidden>
              <span className={cn('h-2.5 w-2.5 rounded-full', dotClass)} />
            </span>
            <AnimatePresence mode="wait">
              {!collapsed && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="flex-1 min-w-0"
                >
                  <p className="text-xs font-medium truncate text-foreground">{engineLabel}</p>
                  <p className="font-mono text-[11px] text-muted-foreground truncate">{engineSub}</p>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </motion.aside>
  );
}
