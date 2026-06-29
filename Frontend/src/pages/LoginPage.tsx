import { useEffect, useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import {
  ArrowRight,
  LogIn,
  UserPlus,
  FileSearch,
  GitBranch,
  Mail,
  CheckCircle2,
  ShieldCheck,
  Wallet,
  AlertTriangle,
  ArrowUp,
  Clock,
  ChevronRight,
  ChevronDown,
  ScrollText,
  Gauge,
  Building2,
  Sparkles,
  Send,
  Twitter,
  Linkedin,
  Github,
  Menu,
  X,
  type LucideIcon,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ConsolePreview } from '@/components/marketing/ConsolePreview';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Navigate, Link, useLocation } from 'react-router-dom';
import { Show, SignInButton } from '@clerk/react';
import { ThemeToggle } from '@/components/layout/ThemeToggle';
import { Logomark } from '@/components/common/Logomark';
import { api, ApiError } from '@/lib/api';
import { cn } from '@/lib/utils';

const CONTACT_EMAIL = 'kamaljit.singh@auxiliobits.com';

// Optional self-serve scheduling link (Cal.com / Calendly / Google Calendar).
// When VITE_DEMO_BOOKING_URL is set, a "Book a demo slot" CTA appears once the
// visitor picks the demo subject — letting them book instantly instead of
// waiting for a reply.
const DEMO_BOOKING_URL = import.meta.env.VITE_DEMO_BOOKING_URL as string | undefined;

/**
 * Public landing / home page (the signed-out entry point).
 *
 * Corporate "Auxilio" identity: a theme-aware canvas (white in light mode, deep
 * slate in dark), a hero anchored on the reconciliation metaphor, a REAL
 * statement preview, and scrolling sections wired to the top-nav anchors. Every
 * claim maps to a shipped capability (classification + confidence, deterministic
 * rule-traced routing, drafted comms, append-only audit log, human approval).
 * Colours are fully token-driven so the page follows the user's theme.
 */
export function LoginPage() {
  return (
    <>
      {/* Already authenticated → straight to the clearing desk. */}
      <Show when="signed-in">
        <Navigate to="/dashboard" replace />
      </Show>
      <Show when="signed-out">
        <HomePage />
      </Show>
    </>
  );
}

const NAV = [
  { id: 'home', label: 'Home' },
  { id: 'exceptions', label: 'Exceptions' },
  { id: 'audit', label: 'Audit Trail' },
  { id: 'rules', label: 'Rules' },
  { id: 'reports', label: 'Reports' },
  { id: 'faq', label: 'FAQ' },
  { id: 'contact', label: 'Contact' },
] as const;
const NAV_IDS = NAV.map((n) => n.id);

/** Lightweight scroll-spy so the top nav highlights the section in view. */
function useScrollSpy(ids: readonly string[]): string {
  const [active, setActive] = useState(ids[0]);
  useEffect(() => {
    const obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries) if (e.isIntersecting) setActive(e.target.id);
      },
      { rootMargin: '-45% 0px -50% 0px', threshold: 0 },
    );
    ids.forEach((id) => {
      const el = document.getElementById(id);
      if (el) obs.observe(el);
    });
    return () => obs.disconnect();
  }, [ids]);
  return active;
}

function HomePage() {
  const reduce = useReducedMotion();
  const active = useScrollSpy(NAV_IDS);

  // Arriving from another route (e.g. the legal pages) with a #section hash:
  // scroll to that section once it's laid out.
  const { hash } = useLocation();
  useEffect(() => {
    if (!hash) return;
    const el = document.getElementById(hash.slice(1));
    if (!el) return;
    const t = setTimeout(
      () => el.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' }),
      60,
    );
    return () => clearTimeout(t);
  }, [hash, reduce]);

  // Mobile nav (the section links are hidden on small screens otherwise).
  const [mobileOpen, setMobileOpen] = useState(false);

  // Header is a flat bar at the top and condenses into a floating pill on scroll.
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const rise = (delay: number) =>
    reduce
      ? {}
      : {
          initial: { opacity: 0, y: 16 },
          animate: { opacity: 1, y: 0 },
          transition: { duration: 0.5, delay, ease: [0.16, 1, 0.3, 1] as const },
        };

  const goTo = (id: string) => () => {
    document
      .getElementById(id)
      ?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
  };

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-background text-foreground">
      {/* ---- Top nav: fixed; flat bar at the top, floats into a pill on scroll ---- */}
      <header
        className={cn(
          'fixed inset-x-0 top-0 z-50 transition-all duration-300',
          scrolled ? 'px-3 pt-3 sm:px-5' : 'px-0 pt-0',
        )}
      >
        <div
          className={cn(
            'mx-auto flex h-16 items-center justify-between transition-all duration-300',
            scrolled
              ? 'max-w-5xl rounded-full border border-border bg-background/90 px-4 shadow-lg shadow-foreground/[0.06] backdrop-blur-md sm:px-6'
              : 'max-w-6xl border border-transparent bg-transparent px-5 sm:px-8',
          )}
        >
          <button onClick={goTo('home')} className="flex items-center gap-2.5" aria-label="LedgerClear — home">
            <Logomark />
            <div className="hidden leading-tight sm:block text-left">
              <p className="font-display text-[15px] font-semibold">LedgerClear</p>
              <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                AP Reconciliation
              </p>
            </div>
          </button>

          <nav className="hidden items-center gap-1 md:flex" aria-label="Sections">
            {NAV.map((n) => (
              <button
                key={n.id}
                onClick={goTo(n.id)}
                aria-current={active === n.id ? 'true' : undefined}
                className={cn(
                  'rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors',
                  active === n.id
                    ? 'border-primary bg-primary/10 text-primary shadow-sm'
                    : 'border-transparent text-muted-foreground hover:border-primary/40 hover:text-foreground',
                )}
              >
                {n.label}
              </button>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            <ThemeToggle />
            <SignInButton mode="modal" forceRedirectUrl="/dashboard">
              <Button size="sm" className="rounded-full">
                <LogIn className="h-4 w-4" />
                Sign in
              </Button>
            </SignInButton>
            {/* Mobile nav toggle — the section links are desktop-only otherwise. */}
            <button
              type="button"
              onClick={() => setMobileOpen((o) => !o)}
              aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
              aria-expanded={mobileOpen}
              className="grid h-9 w-9 place-items-center rounded-full border border-border text-muted-foreground transition-colors hover:text-foreground md:hidden"
            >
              {mobileOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
            </button>
          </div>
        </div>

        {/* Mobile dropdown */}
        {mobileOpen && (
          <div className="mx-3 mt-2 rounded-2xl border border-border bg-background/95 p-2 shadow-lg backdrop-blur-md md:hidden">
            <nav className="flex flex-col" aria-label="Sections">
              {NAV.map((n) => (
                <button
                  key={n.id}
                  onClick={() => {
                    goTo(n.id)();
                    setMobileOpen(false);
                  }}
                  className={cn(
                    'rounded-lg px-3 py-2 text-left text-sm font-medium transition-colors',
                    active === n.id ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                  )}
                >
                  {n.label}
                </button>
              ))}
            </nav>
          </div>
        )}
      </header>

      {/* ===================== HERO ===================== */}
      <section id="home" className="relative scroll-mt-20 overflow-hidden">
        {/* Soft brand gradient glow behind the hero. */}
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              'radial-gradient(60% 55% at 50% 0%, hsl(var(--primary) / 0.10), transparent 70%)',
          }}
          aria-hidden
        />
        {/* Hairline grid — main section ONLY, faded out with a gradient mask. */}
        <div
          className="grid-bg pointer-events-none absolute inset-0"
          style={{
            WebkitMaskImage:
              'radial-gradient(ellipse 80% 65% at 50% 0%, #000 35%, transparent 100%)',
            maskImage:
              'radial-gradient(ellipse 80% 65% at 50% 0%, #000 35%, transparent 100%)',
          }}
          aria-hidden
        />
        <div className="relative">
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-5 pb-16 pt-24 sm:px-8 lg:grid-cols-[1.05fr_0.95fr] lg:gap-16 lg:pb-20 lg:pt-28">
          <div>
            <motion.p
              {...rise(0)}
              className="mb-5 inline-flex items-center gap-2 rounded-full border border-border bg-muted/50 px-3 py-1 font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-primary" />
              Human-in-the-loop AP agent
            </motion.p>

            <motion.h1
              {...rise(0.06)}
              className="font-display text-3xl font-semibold leading-[1.1] tracking-tight sm:text-4xl"
            >
              Clear suspended AP cash —{' '}
              <span className="text-primary">with a trail for every decision.</span>
            </motion.h1>

            <motion.p {...rise(0.12)} className="mt-5 max-w-xl text-base text-muted-foreground">
              Upload an exception queue. The agent classifies each invoice, routes it through your
              rules, drafts the vendor or controller note, and records an audit trail. You review,
              approve, and release the payment.
            </motion.p>

            <motion.div {...rise(0.18)} className="mt-8 flex flex-wrap items-center gap-3">
              <SignInButton mode="modal" forceRedirectUrl="/dashboard">
                <Button size="lg" className="h-12 px-6">
                  Open the clearing desk
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </SignInButton>
              <Button
                size="lg"
                variant="outline"
                className="h-12 px-6"
                onClick={goTo('contact')}
              >
                <UserPlus className="h-4 w-4" />
                Request access
              </Button>
            </motion.div>
          </div>

          <motion.div {...rise(0.16)} className="lg:pl-4">
            <StatementPreview onViewAll={goTo('exceptions')} />
          </motion.div>
        </div>

        {/* Pipeline strip — the actual graph, not generic feature cards. */}
        <div className="mx-auto max-w-6xl px-5 pb-12 sm:px-8">
          <PipelineStrip />
        </div>

        {/* Product preview — a look at the clearing desk in action. */}
        {/* <div className="mx-auto max-w-6xl px-5 pb-20 sm:px-8">
          <p className="mb-4 text-center font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
            A look at the clearing desk
          </p>
          <motion.div {...rise(0.1)}>
            <ConsolePreview />
          </motion.div>
        </div> */}
        </div>
      </section>

      {/* ===================== EXCEPTIONS ===================== */}
      <SectionBand id="exceptions" alt>
        <SectionHead
          eyebrow="Exceptions"
          title="Every exception, classified — and explained."
          lead="The agent reads each invoice, names the exception type, scores its confidence, and writes the reasoning in plain language. Nothing is a black box."
        />
        <div className="mt-10 grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
          <ClassificationCard />
          <div>
            <p className="mb-4 font-mono text-xs uppercase tracking-[0.16em] text-muted-foreground">
              Exception types it handles
            </p>
            <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
              {[
                'Price Variance',
                'Quantity Mismatch',
                'Missing PO',
                'Duplicate Invoice',
                'Unapproved Vendor',
                'GRN Not Received',
                'Tax Discrepancy',
                'Payment Terms',
              ].map((t) => (
                <span
                  key={t}
                  className="rounded-md border border-border bg-card px-3 py-2.5 text-sm text-foreground/85"
                >
                  {t}
                </span>
              ))}
            </div>
          </div>
        </div>
      </SectionBand>

      {/* ===================== AUDIT TRAIL ===================== */}
      <SectionBand id="audit">
        <SectionHead
          eyebrow="Audit Trail"
          title="A trail for every decision."
          lead="Each run writes an append-only log — what the agent saw, which rule fired, and what it produced. Hand an auditor the exact path from invoice to outcome."
        />
        <div className="mt-10 grid gap-6 lg:grid-cols-2 lg:items-center">
          <AuditTrailCard />
          <ul className="space-y-5">
            {[
              { icon: ScrollText, t: 'Append-only by design', d: 'Events are added, never edited — the record of what happened stays intact.' },
              { icon: GitBranch, t: 'Rule trace on every routing', d: 'See the ordered list of rules evaluated and the one that decided the path.' },
              { icon: Sparkles, t: 'Model + prompt version stamped', d: 'Each classification records the model id and prompt version that produced it.' },
            ].map((f) => (
              <FeatureRow key={f.t} icon={f.icon} title={f.t} desc={f.d} />
            ))}
          </ul>
        </div>
      </SectionBand>

      {/* ===================== RULES ===================== */}
      <SectionBand id="rules" alt>
        <SectionHead
          eyebrow="Rules"
          title="Your rules, applied the same way every time."
          lead="Routing is deterministic, not improvised. The agent classifies; your rule engine decides the resolution path and the SLA — identical inputs always reach the same outcome."
        />
        <div className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[
            { path: 'Auto-approve', when: 'Low-risk, within tolerance', tone: 'success' as const },
            { path: 'Request PO', when: 'Missing purchase order', tone: 'warning' as const },
            { path: 'Request GRN', when: 'Goods receipt not posted', tone: 'warning' as const },
            { path: 'Vendor validation', when: 'Unapproved or new vendor', tone: 'warning' as const },
            { path: 'Escalate to controller', when: 'High value or severity', tone: 'danger' as const },
            { path: 'Hold for investigation', when: 'Suspected duplicate', tone: 'danger' as const },
          ].map((r) => (
            <RuleCard key={r.path} {...r} />
          ))}
        </div>
      </SectionBand>

      {/* ===================== REPORTS ===================== */}
      <SectionBand id="reports">
        <SectionHead
          eyebrow="Reports"
          title="See exactly where cash is stuck."
          lead="The clearing desk shows your suspended balance partitioned by what each dollar is waiting on, a priority queue of what to clear first, and a reliability profile for every vendor."
        />
        <div className="mt-10 grid gap-6 sm:grid-cols-3">
          <FeatureTile
            icon={Gauge}
            title="Suspended balance"
            desc="One ledger bar: at-risk, escalated, awaiting review, cleared — by dollar value."
          />
          <FeatureTile
            icon={AlertTriangle}
            title="Priority queue"
            desc="Exceptions ranked by amount, age, severity, path and confidence — work the top first."
          />
          <FeatureTile
            icon={Building2}
            title="Vendor reliability"
            desc="Per-vendor history: duplicates, escalations, missing POs and a reliability score."
          />
        </div>
      </SectionBand>

      {/* ===================== FAQ ===================== */}
      <FaqSection />

      {/* ===================== CONTACT ===================== */}
      <ContactSection />

      {/* ===================== FOOTER ===================== */}
      <SiteFooter goTo={goTo} />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Layout helpers                                                      */
/* ------------------------------------------------------------------ */

function SectionBand({
  id,
  alt,
  children,
}: {
  id: string;
  alt?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className={`scroll-mt-16 ${alt ? 'bg-muted/30' : ''}`}>
      <div className="mx-auto max-w-6xl px-5 py-20 sm:px-8">{children}</div>
    </section>
  );
}

function SectionHead({ eyebrow, title, lead }: { eyebrow: string; title: string; lead: string }) {
  const reduce = useReducedMotion();
  const reveal = reduce
    ? {}
    : {
        initial: { opacity: 0, y: 24 },
        whileInView: { opacity: 1, y: 0 },
        viewport: { once: true, margin: '-80px' },
        transition: { duration: 0.5, ease: [0.16, 1, 0.3, 1] as const },
      };
  return (
    <motion.div {...reveal} className="max-w-2xl">
      <p className="mb-3 font-mono text-xs uppercase tracking-[0.18em] text-primary">
        {eyebrow}
      </p>
      <h2 className="font-display text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h2>
      <p className="mt-4 text-muted-foreground">{lead}</p>
    </motion.div>
  );
}

function FeatureRow({ icon: Icon, title, desc }: { icon: LucideIcon; title: string; desc: string }) {
  return (
    <li className="flex items-start gap-3">
      <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-md bg-primary/10 ring-1 ring-primary/20">
        <Icon className="h-[18px] w-[18px] text-primary" aria-hidden />
      </span>
      <div>
        <p className="text-sm font-medium">{title}</p>
        <p className="mt-0.5 text-sm text-muted-foreground">{desc}</p>
      </div>
    </li>
  );
}

function FeatureTile({ icon: Icon, title, desc }: { icon: LucideIcon; title: string; desc: string }) {
  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <span className="grid h-10 w-10 place-items-center rounded-md bg-primary/10 ring-1 ring-primary/20">
        <Icon className="h-5 w-5 text-primary" aria-hidden />
      </span>
      <h3 className="mt-4 font-medium">{title}</h3>
      <p className="mt-1.5 text-sm text-muted-foreground">{desc}</p>
    </div>
  );
}

function RuleCard({
  path,
  when,
  tone,
}: {
  path: string;
  when: string;
  tone: 'success' | 'warning' | 'danger';
}) {
  const dot = { success: 'bg-settled', warning: 'bg-pending', danger: 'bg-overdue' }[tone];
  return (
    <div className="flex items-start gap-3 rounded-lg border border-border bg-card p-4">
      <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${dot}`} aria-hidden />
      <div className="min-w-0">
        <p className="font-medium">{path}</p>
        <p className="mt-0.5 font-mono text-xs text-muted-foreground">when · {when}</p>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Hero statement preview (matches the in-app Reconciliation Strip)    */
/* ------------------------------------------------------------------ */

function StatementPreview({ onViewAll }: { onViewAll: () => void }) {
  const stats = [
    { label: 'At risk', amount: '$701K', icon: AlertTriangle, ink: 'text-overdue' },
    { label: 'Escalated', amount: '$410K', icon: ArrowUp, ink: 'text-pending' },
    { label: 'Awaiting', amount: '$332K', icon: Clock, ink: 'text-foreground/80' },
    { label: 'Cleared', amount: '$401K', icon: CheckCircle2, ink: 'text-settled' },
  ];
  const rows = [
    { id: 'INV-48213', vendor: 'Halford Logistics', amount: '$182,400', stamp: 'High', variant: 'danger' as const },
    { id: 'INV-48190', vendor: 'Cedar Tooling Co.', amount: '$44,950', stamp: 'Med', variant: 'warning' as const },
    { id: 'INV-48155', vendor: 'Brightpath Media', amount: '$9,120', stamp: 'Cleared', variant: 'success' as const },
  ];

  return (
    <div className="rounded-xl border border-border bg-card text-card-foreground shadow-2xl">
      {/* Balance header */}
      <div className="flex items-end justify-between px-5 pt-5">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-md bg-primary text-primary-foreground">
            <Wallet className="h-5 w-5" aria-hidden />
          </span>
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
              Suspended balance
            </p>
            <p className="font-display text-3xl font-semibold leading-none tracking-tight tabular-nums">
              $1.84M
            </p>
          </div>
        </div>
        <p className="font-mono text-xs text-primary">142 exceptions</p>
      </div>

      {/* Four lifecycle stats */}
      <div className="mt-5 grid grid-cols-2 gap-px border-y border-border bg-border sm:grid-cols-4">
        {stats.map((s) => {
          const Icon = s.icon;
          return (
            <div key={s.label} className="bg-card px-4 py-3.5">
              <span className="grid h-7 w-7 place-items-center rounded-full ring-1 ring-border">
                <Icon className={`h-3.5 w-3.5 ${s.ink}`} aria-hidden />
              </span>
              <p className="mt-2 text-[11px] text-muted-foreground">{s.label}</p>
              <p className={`font-mono text-sm font-medium tabular-nums ${s.ink}`}>{s.amount}</p>
            </div>
          );
        })}
      </div>

      {/* Top exceptions sub-panel */}
      <div className="p-5">
        <div className="rounded-lg border bg-background/40">
          <div className="flex items-center justify-between px-4 py-3">
            <p className="text-sm font-semibold">Top exceptions</p>
            <button
              onClick={onViewAll}
              className="inline-flex items-center gap-1 rounded-md border px-2.5 py-1 font-mono text-[11px] text-muted-foreground hover:text-foreground"
            >
              View all exceptions
              <ArrowRight className="h-3 w-3" />
            </button>
          </div>
          <div className="divide-y">
            {rows.map((r) => (
              <div key={r.id} className="flex items-center justify-between gap-3 px-4 py-3">
                <div className="flex items-center gap-3 min-w-0">
                  <span className="rounded border px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
                    {r.id}
                  </span>
                  <span className="truncate text-sm font-medium">{r.vendor}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="font-mono text-sm tabular-nums">{r.amount}</span>
                  <Stamp variant={r.variant}>{r.stamp}</Stamp>
                  <ChevronRight className="h-4 w-4 text-muted-foreground" aria-hidden />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Section illustrations                                               */
/* ------------------------------------------------------------------ */

function ClassificationCard() {
  return (
    <div className="rounded-xl border border-border bg-card text-card-foreground p-5 shadow-xl">
      <div className="flex items-center justify-between">
        <span className="rounded border px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
          INV-48213
        </span>
        <Stamp variant="danger">Price Variance</Stamp>
      </div>
      <p className="mt-4 font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
        Confidence
      </p>
      <div className="mt-1.5 flex items-center gap-3">
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
          <div className="h-full rounded-full bg-settled" style={{ width: '92%' }} />
        </div>
        <span className="font-mono text-sm font-medium tabular-nums">92%</span>
      </div>
      <p className="mt-4 font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
        Rationale
      </p>
      <p className="mt-1.5 text-sm text-foreground/80">
        Invoiced unit price exceeds the PO price by 14% on 3 line items. Quantity and totals
        otherwise match the receipt — consistent with a price variance, not a duplicate.
      </p>
      <div className="mt-4 flex items-center gap-3 border-t pt-3 font-mono text-[11px] text-muted-foreground">
        <span>severity · HIGH</span>
        <span>·</span>
        <span>route · escalate to controller</span>
      </div>
    </div>
  );
}

function AuditTrailCard() {
  const events = [
    { node: 'ingest', event: '142 rows accepted', t: '09:41:02' },
    { node: 'classify', event: 'price_variance · conf 0.92', t: '09:41:04' },
    { node: 'resolve', event: 'rule R-07 matched → escalate', t: '09:41:04' },
    { node: 'draft', event: 'controller note generated', t: '09:41:05' },
    { node: 'persist', event: 'run snapshot written', t: '09:41:06' },
  ];
  return (
    <div className="rounded-xl border border-border bg-card text-card-foreground p-5 shadow-xl">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">Audit log · run_8f3c</p>
        <span className="inline-flex items-center gap-1.5 rounded-md border border-settled/30 bg-settled/12 px-2 py-0.5 font-mono text-[11px] text-settled">
          append-only
        </span>
      </div>
      <ol className="mt-4 space-y-0">
        {events.map((e, i) => (
          <li key={e.node} className="flex gap-3">
            <div className="flex flex-col items-center">
              <span className="mt-1 h-2 w-2 rounded-full bg-primary" />
              {i < events.length - 1 && <span className="w-px flex-1 bg-border" />}
            </div>
            <div className="pb-4">
              <p className="text-sm">
                <span className="font-mono text-xs text-muted-foreground">{e.node}</span>{' '}
                <span className="font-medium">{e.event}</span>
              </p>
              <p className="font-mono text-[11px] text-muted-foreground">{e.t}</p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

const PIPELINE = [
  { icon: FileSearch, label: 'Ingest & classify', hint: 'every invoice, with a confidence score' },
  { icon: GitBranch, label: 'Route by rule', hint: 'deterministic, fully rule-traced' },
  { icon: Mail, label: 'Draft the note', hint: 'vendor or controller, ready to edit' },
  { icon: CheckCircle2, label: 'Review & clear', hint: 'you approve — cash moves' },
];

function PipelineStrip() {
  const reduce = useReducedMotion();
  const reveal = reduce
    ? {}
    : {
        initial: { opacity: 0, y: 16 },
        whileInView: { opacity: 1, y: 0 },
        viewport: { once: true, margin: '-60px' },
        transition: { duration: 0.5, ease: [0.16, 1, 0.3, 1] as const },
      };
  return (
    <motion.ol
      {...reveal}
      className="grid divide-y divide-border rounded-xl border border-border bg-card lg:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr] lg:divide-y-0"
    >
      {PIPELINE.map((step, i) => {
        const Icon = step.icon;
        return (
          <li key={step.label} className="contents">
            <div className="flex items-start gap-3 p-5">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full ring-1 ring-border">
                <Icon className="h-5 w-5 text-primary" aria-hidden />
              </span>
              <div>
                <p className="font-mono text-[11px] text-muted-foreground">
                  {String(i + 1).padStart(2, '0')}
                </p>
                <p className="text-sm font-medium">{step.label}</p>
                <p className="text-xs text-muted-foreground">{step.hint}</p>
              </div>
            </div>
            {i < PIPELINE.length - 1 && (
              <div className="hidden items-center justify-center lg:flex" aria-hidden>
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              </div>
            )}
          </li>
        );
      })}
    </motion.ol>
  );
}

function Stamp({
  variant,
  children,
}: {
  variant: 'danger' | 'warning' | 'success';
  children: React.ReactNode;
}) {
  const cls = {
    danger: 'border-overdue/30 bg-overdue/12 text-overdue',
    warning: 'border-pending/30 bg-pending/12 text-pending',
    success: 'border-settled/30 bg-settled/12 text-settled',
  }[variant];
  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-semibold ${cls}`}>
      {children}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* FAQ section (accordion)                                             */
/* ------------------------------------------------------------------ */

const FAQS = [
  {
    q: 'What can I upload, and how big can it be?',
    a: 'Upload an exception queue as CSV or JSON (up to 25 MB). The agent ingests each row and quarantines anything malformed, so the rest of the run still processes cleanly.',
  },
  {
    q: 'Does the agent send anything on its own?',
    a: 'No — it only drafts. Every vendor or controller message waits for you to review, edit, and approve before it is sent. You stay in control of every send and every payment release.',
  },
  {
    q: 'How does it decide what to do with each invoice?',
    a: 'It classifies the exception with a confidence score and a plain-language rationale, then a deterministic rule engine picks the resolution path and SLA — identical inputs always reach the same outcome.',
  },
  {
    q: 'Is every decision auditable?',
    a: 'Yes. Each run writes an append-only audit log capturing what the agent saw, which rule fired, and the model and prompt version behind every classification.',
  },
  {
    q: 'Where is my data stored?',
    a: 'Run data is persisted to your configured database and scoped to your organization, so one tenant can never read another’s runs. History survives restarts and can be re-opened anytime.',
  },
  {
    q: 'Can I review past runs?',
    a: 'Yes — the run history picker lists every run from the database; select any one to re-open its results, metrics, drafts, and audit trail.',
  },
];

function FaqSection() {
  const [open, setOpen] = useState<number | null>(0);
  return (
    <SectionBand id="faq" alt>
      <SectionHead
        eyebrow="FAQ"
        title="Frequently Asked Questions"
        lead="Answers to common questions about LedgerClear and its features. If you have any other questions, please don't hesitate to contact us."
      />
      <div className="mt-10 max-w-3xl space-y-3">
        {FAQS.map((f, i) => {
          const isOpen = open === i;
          return (
            <div key={f.q} className="overflow-hidden rounded-xl border border-border bg-card">
              <button
                type="button"
                aria-expanded={isOpen}
                onClick={() => setOpen(isOpen ? null : i)}
                className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left transition-colors hover:bg-muted/50"
              >
                <span className="font-medium">{f.q}</span>
                <ChevronDown
                  className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200 ${
                    isOpen ? 'rotate-180' : ''
                  }`}
                />
              </button>
              {isOpen && (
                <p className="px-5 pb-4 text-sm leading-relaxed text-muted-foreground">{f.a}</p>
              )}
            </div>
          );
        })}
      </div>
    </SectionBand>
  );
}

/* ------------------------------------------------------------------ */
/* Contact section (TailGrids "AISpace"-style: info cards + form)      */
/* ------------------------------------------------------------------ */

function ContactSection() {
  const reduce = useReducedMotion();
  const reveal = reduce
    ? {}
    : {
        initial: { opacity: 0, y: 24 },
        whileInView: { opacity: 1, y: 0 },
        viewport: { once: true, margin: '-80px' },
        transition: { duration: 0.5, ease: [0.16, 1, 0.3, 1] as const },
      };

  const [form, setForm] = useState({
    firstName: '',
    lastName: '',
    email: '',
    subject: '',
    message: '',
  });
  const [agree, setAgree] = useState(false);
  const [sent, setSent] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hp, setHp] = useState(''); // honeypot — bots fill it, humans don't

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await api.submitContact({
        name: `${form.firstName} ${form.lastName}`.trim(),
        email: form.email,
        subject: form.subject || 'Website enquiry',
        message: form.message,
        company_website: hp,
      });
      setSent(true);
      // Clear the inputs on success so the form resets to empty.
      setForm({ firstName: '', lastName: '', email: '', subject: '', message: '' });
      setAgree(false);
      setHp('');
      // Re-enable the form after a few seconds so another message can be sent.
      setTimeout(() => setSent(false), 4000);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : `Could not send right now — please email us at ${CONTACT_EMAIL}.`,
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section id="contact" className="scroll-mt-16">
      <div className="mx-auto max-w-6xl px-5 pb-20 pt-16 sm:px-8">
        {/* Gradient banner with a faded hairline grid inside the blue. */}
        <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-primary to-[hsl(214_94%_72%)] px-6 pb-44 pt-12 text-center sm:px-10">
          <div
            className="pointer-events-none absolute inset-0"
            style={{
              backgroundImage:
                'repeating-linear-gradient(to right, rgba(255,255,255,0.14) 0 1px, transparent 1px 48px), repeating-linear-gradient(to bottom, rgba(255,255,255,0.14) 0 1px, transparent 1px 48px)',
              WebkitMaskImage:
                'radial-gradient(ellipse 85% 70% at 50% 0%, #000 35%, transparent 100%)',
              maskImage:
                'radial-gradient(ellipse 85% 70% at 50% 0%, #000 35%, transparent 100%)',
            }}
            aria-hidden
          />
          <div className="relative">
            <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-white/80">
              Reach out anytime
            </p>
            <h2 className="mt-3 font-display text-2xl font-semibold tracking-tight text-white sm:text-3xl">
              Let&apos;s Stay Connected
            </h2>
            <p className="mx-auto mt-3 max-w-xl text-sm text-white/85">
              Questions about your AP backlog or want a walkthrough? Send a note and we&apos;ll get
              back to you.
            </p>
          </div>
        </div>

        {/* Overlapping form card */}
        <motion.form
          {...reveal}
          onSubmit={onSubmit}
          className="relative z-10 mx-auto -mt-32 max-w-xl rounded-2xl border border-border bg-card p-6 shadow-2xl sm:p-8"
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium">First Name</span>
              <Input
                required
                value={form.firstName}
                onChange={(e) => setForm((f) => ({ ...f, firstName: e.target.value }))}
                placeholder="Kate"
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium">Last Name</span>
              <Input
                required
                value={form.lastName}
                onChange={(e) => setForm((f) => ({ ...f, lastName: e.target.value }))}
                placeholder="Williamson"
              />
            </label>
          </div>
          <label className="mt-4 block">
            <span className="mb-1.5 block text-sm font-medium">Email</span>
            <Input
              required
              type="email"
              value={form.email}
              onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
              placeholder="yourname@company.com"
            />
          </label>
          <div className="mt-4">
            <span className="mb-1.5 block text-sm font-medium">Subject</span>
            <Select
              value={form.subject}
              onValueChange={(v) => setForm((f) => ({ ...f, subject: v }))}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select subject" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="General enquiry">General enquiry</SelectItem>
                <SelectItem value="Book a demo">Book a demo</SelectItem>
                <SelectItem value="Pricing & plans">Pricing &amp; plans</SelectItem>
                <SelectItem value="Technical support">Technical support</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {form.subject === 'Book a demo' && DEMO_BOOKING_URL && (
            <a
              href={DEMO_BOOKING_URL}
              target="_blank"
              rel="noreferrer"
              className="mt-3 flex items-center gap-2 rounded-xl border border-primary/30 bg-primary/5 px-4 py-3 text-sm font-medium text-primary transition-colors hover:bg-primary/10"
            >
              <Clock className="h-4 w-4 shrink-0" />
              Prefer to pick a time now? Book a demo slot →
            </a>
          )}
          <label className="mt-4 block">
            <span className="mb-1.5 block text-sm font-medium">Message</span>
            <textarea
              required
              rows={4}
              value={form.message}
              onChange={(e) => setForm((f) => ({ ...f, message: e.target.value }))}
              placeholder="Type your message here"
              className="flex w-full rounded-xl border border-input bg-background px-4 py-2.5 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            />
          </label>
          <label className="mt-4 flex items-start gap-2.5">
            <Checkbox
              id="agree-privacy"
              checked={agree}
              onCheckedChange={(v) => setAgree(v === true)}
              className="mt-0.5"
            />
            <span className="text-sm text-muted-foreground">
              You agree to our{' '}
              <Link to="/privacy" className="text-primary hover:underline">
                friendly privacy policy
              </Link>
              .
            </span>
          </label>
          {/* Honeypot: hidden from humans; bots that fill it get silently dropped. */}
          <input
            type="text"
            name="company_website"
            tabIndex={-1}
            autoComplete="off"
            value={hp}
            onChange={(e) => setHp(e.target.value)}
            className="hidden"
            aria-hidden="true"
          />
          <Button type="submit" size="lg" disabled={!agree || submitting || sent} className="mt-6 w-full">
            {submitting ? 'Sending…' : sent ? 'Message sent' : 'Send Message'}
            <Send className="h-4 w-4" />
          </Button>
          {sent && (
            <p className="mt-3 text-center text-sm text-settled">
              Thanks — we&apos;ve received your message and will be in touch.
            </p>
          )}
          {error && <p className="mt-3 text-center text-sm text-overdue">{error}</p>}
        </motion.form>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Footer (TailGrids "AISpace"-style: brand + columns + bottom bar)    */
/* ------------------------------------------------------------------ */

type FooterLink = {
  label: string;
  to?: string;
  href?: string;
  onClick?: () => void;
  external?: boolean;
};

function FooterCol({ title, links }: { title: string; links: FooterLink[] }) {
  return (
    <div>
      <p className="mb-3 font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
        {title}
      </p>
      <ul className="space-y-2.5 text-sm">
        {links.map((l) => (
          <li key={l.label}>
            {l.to ? (
              <Link to={l.to} className="text-muted-foreground transition-colors hover:text-foreground">
                {l.label}
              </Link>
            ) : l.href ? (
              <a
                href={l.href}
                className="text-muted-foreground transition-colors hover:text-foreground"
                {...(l.external ? { target: '_blank', rel: 'noreferrer' } : {})}
              >
                {l.label}
              </a>
            ) : (
              <button
                onClick={l.onClick}
                className="text-left text-muted-foreground transition-colors hover:text-foreground"
              >
                {l.label}
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function NewsletterBand() {
  const [email, setEmail] = useState('');
  const [subscribed, setSubscribed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [hp, setHp] = useState(''); // honeypot
  const onSubscribe = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await api.subscribe(email, hp);
      setSubscribed(true);
      // Clear the input on success.
      setEmail('');
      setHp('');
      // Re-enable the field after a few seconds so another address can subscribe.
      setTimeout(() => setSubscribed(false), 4000);
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : 'Could not subscribe right now.');
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="grid gap-6 rounded-2xl border border-border bg-card p-6 shadow-sm sm:grid-cols-[1fr_auto] sm:items-center sm:p-8">
      <div>
        <h3 className="font-display text-xl font-semibold tracking-tight">Subscribe to our newsletter</h3>
        <p className="mt-1.5 text-sm text-muted-foreground">
          Product updates and finance-ops tips. Your privacy matters to us — read our full{' '}
          <Link to="/privacy" className="text-primary hover:underline">
            Privacy Policy
          </Link>
          .
        </p>
        {subscribed && (
          <p className="mt-2 text-sm text-settled">Thanks — you&apos;re subscribed.</p>
        )}
        {err && <p className="mt-2 text-sm text-overdue">{err}</p>}
      </div>
      <form onSubmit={onSubscribe} className="flex w-full gap-2 sm:w-auto">
        <Input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Enter your email"
          className="sm:w-64"
          disabled={subscribed}
        />
        <input
          type="text"
          name="company_website"
          tabIndex={-1}
          autoComplete="off"
          value={hp}
          onChange={(e) => setHp(e.target.value)}
          className="hidden"
          aria-hidden="true"
        />
        <Button type="submit" className="shrink-0" disabled={busy || subscribed}>
          {busy ? 'Subscribing…' : subscribed ? 'Subscribed' : 'Subscribe'}
        </Button>
      </form>
    </div>
  );
}

function SiteFooter({ goTo }: { goTo: (id: string) => () => void }) {
  const socials = [
    { icon: Twitter, label: 'X (Twitter)', href: 'https://twitter.com' },
    { icon: Linkedin, label: 'LinkedIn', href: 'https://linkedin.com' },
    { icon: Github, label: 'GitHub', href: 'https://github.com' },
  ];
  return (
    <footer className="border-t border-border bg-muted/30">
      <div className="mx-auto max-w-6xl px-5 py-14 sm:px-8">
        <NewsletterBand />

        <div className="mt-12 grid gap-10 md:grid-cols-[1.6fr_1fr_1fr_1fr_1fr]">
          {/* Brand */}
          <div className="max-w-xs">
            <div className="flex items-center gap-2.5">
              <Logomark />
              <p className="font-display text-[15px] font-semibold">LedgerClear</p>
            </div>
            <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
              An operator console for clearing AP invoice exceptions — classified, rule-routed,
              drafted, and audit-logged, with a human in the loop.
            </p>
            <p className="mt-4 flex items-center gap-2 text-xs text-muted-foreground">
              <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-primary" />
              Every routing is rule-traced and audit-logged.
            </p>
          </div>

          <FooterCol
            title="Product"
            links={[
              { label: 'Exceptions', onClick: goTo('exceptions') },
              { label: 'Audit Trail', onClick: goTo('audit') },
              { label: 'Rules', onClick: goTo('rules') },
              { label: 'Reports', onClick: goTo('reports') },
            ]}
          />

          <FooterCol
            title="Company"
            links={[
              { label: 'About', onClick: goTo('home') },
              { label: 'Contact', onClick: goTo('contact') },
              { label: 'Email us', href: `mailto:${CONTACT_EMAIL}` },
            ]}
          />
          <FooterCol
            title="Support"
            links={[
              { label: 'FAQ', onClick: goTo('faq') },
              { label: 'Help Center', href: `mailto:${CONTACT_EMAIL}` },
              { label: 'Privacy Policy', to: '/privacy' },
              { label: 'Terms of Service', to: '/terms' },
            ]}
          />

          {/* Connect */}
          <div>
            <p className="mb-3 font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
              Connect
            </p>
            <ul className="space-y-2.5 text-sm">
              {socials.map((s) => {
                const Icon = s.icon;
                return (
                  <li key={s.label}>
                    <a
                      href={s.href}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-2 text-muted-foreground transition-colors hover:text-foreground"
                    >
                      <Icon className="h-4 w-4 shrink-0" />
                      {s.label}
                    </a>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>

        <div className="mt-12 flex flex-col items-center justify-between gap-3 border-t border-border pt-6 sm:flex-row">
          <p className="font-mono text-xs text-muted-foreground">
            © Copyright 2026 · LedgerClear
          </p>
          <nav className="flex items-center gap-4 font-mono text-xs text-muted-foreground" aria-label="Legal">
            <Link to="/terms" className="hover:text-foreground">Terms &amp; Conditions</Link>
            <span aria-hidden>|</span>
            <Link to="/privacy" className="hover:text-foreground">Privacy Policy</Link>
          </nav>
        </div>
      </div>
    </footer>
  );
}

