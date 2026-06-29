/**
 * The LedgerClear logomark — a blue chip with ledger rules and a checkmark.
 * Shared by the public marketing header/footer and the legal pages so the brand
 * stays identical everywhere.
 */
export function Logomark() {
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
