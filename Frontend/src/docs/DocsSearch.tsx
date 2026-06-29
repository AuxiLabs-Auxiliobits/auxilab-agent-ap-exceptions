import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, CornerDownLeft } from 'lucide-react';
import { blocksToText } from './blocks';
import { DOC_CONTENT } from './content';
import { DOC_GROUPS, ALL_DOC_PAGES } from './manifest';

// Pre-built search index: title + summary + full body text, lowercased.
const GROUP_OF: Record<string, string> = {};
for (const g of DOC_GROUPS) for (const p of g.pages) GROUP_OF[p.slug] = g.title;

const INDEX = ALL_DOC_PAGES.map((p) => ({
  slug: p.slug,
  title: p.title,
  summary: p.summary,
  group: GROUP_OF[p.slug] ?? '',
  haystack: `${p.title} ${p.summary} ${blocksToText(DOC_CONTENT[p.slug] ?? [])}`.toLowerCase(),
}));

interface SearchCtx {
  open: () => void;
}
const Ctx = createContext<SearchCtx | null>(null);

export function useDocsSearch(): SearchCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error('useDocsSearch must be used within DocsSearchProvider');
  return c;
}

export function DocsSearchProvider({ children }: { children: ReactNode }) {
  const [isOpen, setOpen] = useState(false);

  // Global ⌘K / Ctrl+K to open.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen(true);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const value = useMemo(() => ({ open: () => setOpen(true) }), []);

  return (
    <Ctx.Provider value={value}>
      {children}
      {isOpen && <CommandPalette onClose={() => setOpen(false)} />}
    </Ctx.Provider>
  );
}

function CommandPalette({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return INDEX.slice(0, 8);
    return INDEX.filter((r) => q.split(/\s+/).every((t) => r.haystack.includes(t))).slice(0, 12);
  }, [query]);

  const go = useCallback(
    (slug: string) => {
      navigate(`/docs/${slug}`);
      onClose();
    },
    [navigate, onClose],
  );

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') onClose();
    else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === 'Enter' && results[active]) {
      e.preventDefault();
      go(results[active].slug);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-[12vh]" role="dialog" aria-modal="true">
      <button className="absolute inset-0 bg-foreground/40 backdrop-blur-sm" aria-label="Close search" onClick={onClose} />
      <div
        className="relative w-full max-w-xl overflow-hidden rounded-xl border border-border bg-popover text-popover-foreground shadow-2xl"
        onKeyDown={onKeyDown}
      >
        <div className="flex items-center gap-3 border-b border-border px-4">
          <Search className="h-4 w-4 text-muted-foreground" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            placeholder="Search documentation…"
            className="h-12 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
          <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
            Esc
          </kbd>
        </div>

        <ul className="max-h-[50vh] overflow-y-auto p-2">
          {results.map((r, i) => (
            <li key={r.slug}>
              <button
                onMouseEnter={() => setActive(i)}
                onClick={() => go(r.slug)}
                className={`flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2.5 text-left ${
                  i === active ? 'bg-primary/10' : 'hover:bg-muted'
                }`}
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium text-foreground">{r.title}</span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {r.group} · {r.summary}
                  </span>
                </span>
                {i === active && <CornerDownLeft className="h-4 w-4 shrink-0 text-muted-foreground" />}
              </button>
            </li>
          ))}
          {results.length === 0 && (
            <li className="px-3 py-6 text-center text-sm text-muted-foreground">No results for “{query}”.</li>
          )}
        </ul>
      </div>
    </div>
  );
}

/** A button styled like a search input that opens the command palette. */
export function SearchTrigger({ className = '', big = false }: { className?: string; big?: boolean }) {
  const { open } = useDocsSearch();
  return (
    <button
      onClick={open}
      className={`group flex items-center gap-2.5 rounded-full border border-input bg-background text-muted-foreground transition-colors hover:border-primary/40 ${
        big ? 'h-12 px-4 text-sm' : 'h-9 px-3 text-sm'
      } ${className}`}
    >
      <Search className={big ? 'h-[18px] w-[18px]' : 'h-4 w-4'} />
      <span className="flex-1 text-left">Search documentation…</span>
      <kbd className="hidden rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px] sm:inline-block">
        Ctrl + K
      </kbd>
    </button>
  );
}
