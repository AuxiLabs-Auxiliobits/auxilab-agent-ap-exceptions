import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { LogIn } from 'lucide-react';
import { SignInButton } from '@clerk/react';
import { ThemeToggle } from '@/components/layout/ThemeToggle';
import { Logomark } from '@/components/common/Logomark';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

// Mirrors the homepage top nav. Links jump back to the marketing page and scroll
// to the matching section (the homepage reads the #hash on arrival).
const NAV = [
  { id: 'home', label: 'Home' },
  { id: 'exceptions', label: 'Exceptions' },
  { id: 'audit', label: 'Audit Trail' },
  { id: 'rules', label: 'Rules' },
  { id: 'reports', label: 'Reports' },
  { id: 'faq', label: 'FAQ' },
  { id: 'contact', label: 'Contact' },
];

/**
 * Public legal pages (Privacy Policy, Terms of Service).
 *
 * Theme-aware, content-first layout that mirrors the corporate "Auxilio"
 * landing identity. The copy below is a professional starting template — have
 * it reviewed by counsel before relying on it in production.
 */

const LAST_UPDATED = 'June 15, 2026';
const CONTACT_EMAIL = 'kamaljit.singh@auxiliobits.com';

interface Section {
  heading: string;
  body: string[];
}

function LegalLayout({
  title,
  intro,
  sections,
}: {
  title: string;
  intro: string;
  sections: Section[];
}) {
  // Same behaviour as the homepage header: a flat bar at the top that condenses
  // into a floating pill once the page is scrolled.
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-background text-foreground">
      {/* ---- Top bar: mirrors the homepage header (brand + section nav) ---- */}
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
          <Link to="/login" className="flex items-center gap-2.5" aria-label="LedgerClear — home">
            <Logomark />
            <div className="hidden leading-tight sm:block text-left">
              <p className="font-display text-[15px] font-semibold">LedgerClear</p>
              <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                AP Reconciliation
              </p>
            </div>
          </Link>

          <nav className="hidden items-center gap-1 md:flex" aria-label="Sections">
            {NAV.map((n) => (
              <Link
                key={n.id}
                to={n.id === 'home' ? '/login' : `/login#${n.id}`}
                className="rounded-full border border-transparent px-3.5 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
              >
                {n.label}
              </Link>
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
          </div>
        </div>
      </header>

      {/* ---- Document ---- */}
      <main className="mx-auto max-w-3xl px-5 pb-14 pt-24 sm:px-8">
        <p className="font-mono text-xs uppercase tracking-[0.18em] text-primary">Legal</p>
        <h1 className="mt-3 font-display text-4xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-2 font-mono text-xs text-muted-foreground">Last updated · {LAST_UPDATED}</p>
        <p className="mt-6 text-muted-foreground">{intro}</p>

        <div className="mt-10 space-y-10">
          {sections.map((s, i) => (
            <section key={s.heading}>
              <h2 className="font-display text-xl font-semibold tracking-tight">
                <span className="mr-2 font-mono text-sm text-muted-foreground">
                  {String(i + 1).padStart(2, '0')}
                </span>
                {s.heading}
              </h2>
              <div className="mt-3 space-y-3">
                {s.body.map((p, j) => (
                  <p key={j} className="text-sm leading-relaxed text-foreground/85">
                    {p}
                  </p>
                ))}
              </div>
            </section>
          ))}
        </div>

        <div className="mt-12 rounded-lg border border-border bg-muted/40 p-5">
          <p className="text-sm text-muted-foreground">
            Questions about this document? Contact us at{' '}
            <a
              href={`mailto:${CONTACT_EMAIL}`}
              className="font-medium text-primary hover:underline"
            >
              {CONTACT_EMAIL}
            </a>
            .
          </p>
        </div>

        <footer className="mt-12 border-t border-border pt-6">
          <nav className="flex flex-wrap items-center gap-x-6 gap-y-2 font-mono text-xs text-muted-foreground" aria-label="Legal">
            <Link to="/privacy" className="hover:text-foreground">Privacy Policy</Link>
            <Link to="/terms" className="hover:text-foreground">Terms of Service</Link>
            <Link to="/login" className="hover:text-foreground">Home</Link>
          </nav>
          <p className="mt-4 font-mono text-xs text-muted-foreground">
            © LedgerClear · AP Reconciliation
          </p>
        </footer>
      </main>
    </div>
  );
}

export function PrivacyPage() {
  return (
    <LegalLayout
      title="Privacy Policy"
      intro="This Privacy Policy explains what information LedgerClear (“we”, “us”) collects when you use the service, how we use it, and the choices you have. It applies to the application and the data you upload to process accounts-payable exceptions."
      sections={[
        {
          heading: 'Information we collect',
          body: [
            'Account information. When you sign in, our authentication provider supplies a user identifier and the email address associated with your account. We use this to authenticate you and scope your data to your organization.',
            'Operational data. When you upload an exception queue (CSV or JSON), we process the invoice, vendor, amount, and related fields it contains in order to classify exceptions, route them, and draft communications.',
            'Usage data. We record run metadata — timestamps, status, row counts, and an append-only audit log of the steps the agent took — so that every decision is traceable.',
          ],
        },
        {
          heading: 'How we use information',
          body: [
            'We use the data you provide to deliver the service: classifying invoice exceptions, applying your routing rules, generating draft messages for your review, and producing dashboards and audit trails.',
            'We do not sell your data. We do not use the contents of your uploaded queues to train third-party models without your explicit instruction.',
          ],
        },
        {
          heading: 'Data storage and retention',
          body: [
            'Run data is stored in your configured database so that history survives restarts and can be re-opened later. You control retention by deleting runs in your database.',
            'We retain account identifiers for as long as your account is active. You may request deletion of your data at any time using the contact details below.',
          ],
        },
        {
          heading: 'Sharing and processors',
          body: [
            'We rely on a small number of service providers to operate — for example, an authentication provider, a database host, and (when you enable sending) email or chat delivery providers. These processors act on our instructions and only receive the data needed to perform their function.',
            'We may disclose information if required by law or to protect the rights, safety, and security of our users and service.',
          ],
        },
        {
          heading: 'Security',
          body: [
            'We apply administrative and technical safeguards appropriate to the sensitivity of finance data, including authenticated access and tenant scoping so that one organization cannot read another’s runs.',
            'No method of transmission or storage is perfectly secure; we cannot guarantee absolute security, but we work to protect your information and to disclose incidents as required.',
          ],
        },
        {
          heading: 'Your rights',
          body: [
            'Depending on your location, you may have the right to access, correct, export, or delete your personal information, and to object to or restrict certain processing.',
            'To exercise any of these rights, contact us using the email address below and we will respond within a reasonable period.',
          ],
        },
        {
          heading: 'Changes to this policy',
          body: [
            'We may update this Privacy Policy from time to time. When we make material changes, we will update the “Last updated” date above and, where appropriate, provide additional notice.',
          ],
        },
      ]}
    />
  );
}

export function TermsPage() {
  return (
    <LegalLayout
      title="Terms of Service"
      intro="These Terms of Service govern your access to and use of the LedgerClear AP exception-clearing service. By using the service you agree to these terms. If you are using the service on behalf of an organization, you agree on its behalf."
      sections={[
        {
          heading: 'The service',
          body: [
            'LedgerClear helps finance teams triage accounts-payable exceptions: it classifies uploaded invoices, routes them through deterministic rules, drafts communications, and records an audit trail for your review and approval.',
            'The agent assists with — but does not replace — human judgment. A person reviews and approves every outbound communication and payment decision.',
          ],
        },
        {
          heading: 'Your responsibilities',
          body: [
            'You are responsible for the accuracy and lawfulness of the data you upload, for keeping your credentials secure, and for the decisions you approve within the service.',
            'You agree not to misuse the service, attempt to access data that is not yours, interfere with its operation, or use it to violate any applicable law or third-party right.',
          ],
        },
        {
          heading: 'Acceptable use',
          body: [
            'You may use the service only for legitimate business purposes related to processing your own organization’s accounts-payable exceptions.',
            'You must not upload malware, attempt to reverse engineer the service except as permitted by law, or use it to send unsolicited or deceptive communications.',
          ],
        },
        {
          heading: 'Intellectual property',
          body: [
            'We retain all rights in the service, including its software, design, and documentation. You retain all rights in the data you upload.',
            'You grant us a limited license to process your data solely to provide the service to you.',
          ],
        },
        {
          heading: 'Disclaimers',
          body: [
            'The service is provided “as is” and “as available”. To the maximum extent permitted by law, we disclaim all warranties, express or implied, including merchantability, fitness for a particular purpose, and non-infringement.',
            'Automated classifications and drafts are suggestions. You are responsible for reviewing them before acting.',
          ],
        },
        {
          heading: 'Limitation of liability',
          body: [
            'To the maximum extent permitted by law, we will not be liable for any indirect, incidental, special, consequential, or punitive damages, or for any loss of profits, revenues, or data, arising out of or related to your use of the service.',
          ],
        },
        {
          heading: 'Changes and termination',
          body: [
            'We may modify these terms or the service from time to time. Continued use after changes take effect constitutes acceptance of the updated terms.',
            'You may stop using the service at any time. We may suspend or terminate access for conduct that violates these terms or that creates risk to the service or other users.',
          ],
        },
        {
          heading: 'Contact',
          body: [
            'Questions about these terms can be sent to the contact email below.',
          ],
        },
      ]}
    />
  );
}
