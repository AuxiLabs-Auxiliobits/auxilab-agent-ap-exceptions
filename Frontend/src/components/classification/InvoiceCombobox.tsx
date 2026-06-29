import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, Check } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface InvoiceOption {
  id: string;
  vendor?: string;
}

interface InvoiceComboboxProps {
  value: string;
  onChange: (value: string) => void;
  options: InvoiceOption[];
  /** Fired when an option is picked from the list (id is the chosen invoice). */
  onSelect?: (id: string) => void;
  placeholder?: string;
  disabled?: boolean;
}

/**
 * Type-to-filter invoice picker. A styled, theme-aware replacement for the
 * native <input list> + <datalist> (which renders an unstyled, mispositioned
 * popup). Supports keyboard navigation (↑/↓/Enter/Esc) and click-to-select.
 */
export function InvoiceCombobox({
  value,
  onChange,
  options,
  onSelect,
  placeholder,
  disabled,
}: InvoiceComboboxProps) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);

  const filtered = useMemo(() => {
    const q = value.trim().toLowerCase();
    if (!q) return options;
    return options.filter(
      (o) =>
        o.id.toLowerCase().includes(q) || (o.vendor?.toLowerCase().includes(q) ?? false),
    );
  }, [options, value]);

  // Close when clicking outside.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  // Reset / clamp the active row whenever the visible list changes.
  useEffect(() => {
    setActive((a) => Math.min(Math.max(a, 0), Math.max(filtered.length - 1, 0)));
  }, [filtered.length]);

  // Keep the highlighted row scrolled into view during keyboard nav.
  useEffect(() => {
    if (!open || !listRef.current) return;
    const el = listRef.current.children[active] as HTMLElement | undefined;
    el?.scrollIntoView({ block: 'nearest' });
  }, [active, open]);

  const choose = (id: string) => {
    onChange(id);
    setOpen(false);
    onSelect?.(id);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (!open) setOpen(true);
      else setActive((a) => Math.min(a + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === 'Enter') {
      if (open && filtered[active]) {
        e.preventDefault();
        choose(filtered[active].id);
      }
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  const normalizedValue = value.trim().toUpperCase();

  return (
    <div ref={rootRef} className="relative">
      <div className="relative">
        <input
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-controls="invoice-combobox-list"
          aria-autocomplete="list"
          autoComplete="off"
          disabled={disabled}
          value={value}
          placeholder={placeholder}
          onChange={(e) => {
            onChange(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          className="flex h-10 w-full rounded-xl border border-input bg-background px-4 py-2 pr-10 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 transition-all"
        />
        <button
          type="button"
          tabIndex={-1}
          aria-hidden
          disabled={disabled}
          onClick={() => setOpen((o) => !o)}
          className="absolute right-2 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded text-muted-foreground hover:text-foreground disabled:opacity-50"
        >
          <ChevronDown className={cn('h-4 w-4 transition-transform duration-200', open && 'rotate-180')} />
        </button>
      </div>

      {open && (
        <ul
          id="invoice-combobox-list"
          ref={listRef}
          role="listbox"
          className="absolute z-50 mt-1.5 max-h-64 w-full overflow-auto rounded-xl border border-border bg-popover p-1 text-popover-foreground shadow-lg"
        >
          {filtered.length === 0 ? (
            <li className="px-3 py-6 text-center text-sm text-muted-foreground">
              No invoices match “{value.trim()}”.
            </li>
          ) : (
            filtered.map((o, i) => {
              const isActive = i === active;
              const isSelected = o.id.toUpperCase() === normalizedValue;
              return (
                <li key={o.id} role="option" aria-selected={isSelected}>
                  <button
                    type="button"
                    onMouseEnter={() => setActive(i)}
                    onClick={() => choose(o.id)}
                    className={cn(
                      'flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2 text-left transition-colors',
                      isActive ? 'bg-accent text-accent-foreground' : 'hover:bg-muted',
                    )}
                  >
                    <span className="flex min-w-0 flex-col">
                      <span className="font-mono text-[13px] font-medium">{o.id}</span>
                      {o.vendor && (
                        <span className="truncate text-xs text-muted-foreground">{o.vendor}</span>
                      )}
                    </span>
                    {isSelected && <Check className="h-4 w-4 shrink-0 text-primary" />}
                  </button>
                </li>
              );
            })
          )}
        </ul>
      )}
    </div>
  );
}
