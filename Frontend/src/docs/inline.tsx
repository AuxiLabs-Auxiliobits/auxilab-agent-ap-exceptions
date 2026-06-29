import { Fragment, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

// Splits on **bold**, `code`, and [label](href), keeping the delimiters so each
// token can be rendered as the right element. Nesting isn't supported (not
// needed by the docs content) — tokens are matched left-to-right.
const TOKEN = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g;
const LINK = /^\[([^\]]+)\]\(([^)]+)\)$/;

/** Render a string with the lightweight inline syntax into React nodes. */
export function renderInline(text: string): ReactNode {
  const parts = text.split(TOKEN);
  return parts.map((part, i) => {
    if (!part) return null;
    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <strong key={i} className="font-semibold text-foreground">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <code
          key={i}
          className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[0.85em] text-foreground"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    const m = LINK.exec(part);
    if (m) {
      const [, label, href] = m;
      const cls = 'font-medium text-primary underline-offset-4 hover:underline';
      return href.startsWith('/') ? (
        <Link key={i} to={href} className={cls}>
          {label}
        </Link>
      ) : (
        <a key={i} href={href} target="_blank" rel="noreferrer" className={cls}>
          {label}
        </a>
      );
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}
