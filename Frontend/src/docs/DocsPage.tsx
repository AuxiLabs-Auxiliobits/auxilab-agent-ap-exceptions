import { useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, ArrowRight, Home } from 'lucide-react';
import { DocBlocks } from './DocBlocks';
import { getDocBlocks } from './loadDocs';
import { ALL_DOC_PAGES, findDocIndex } from './manifest';

/** Renders one documentation page by slug, with breadcrumb + prev/next nav. */
export function DocsPage() {
  const { slug = '' } = useParams();
  const content = getDocBlocks(slug);
  const idx = findDocIndex(slug);
  const meta = idx >= 0 ? ALL_DOC_PAGES[idx] : null;
  const prev = idx > 0 ? ALL_DOC_PAGES[idx - 1] : null;
  const next = idx >= 0 && idx < ALL_DOC_PAGES.length - 1 ? ALL_DOC_PAGES[idx + 1] : null;

  // Scroll to top whenever the page changes.
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [slug]);

  if (!content || !meta) {
    return (
      <div className="py-16 text-center">
        <p className="text-5xl font-semibold text-muted-foreground">404</p>
        <p className="mt-3 text-lg">That documentation page doesn’t exist.</p>
        <Link to="/docs" className="mt-4 inline-flex items-center gap-1 text-primary hover:underline">
          <Home className="h-4 w-4" /> Back to docs home
        </Link>
      </div>
    );
  }

  return (
    <article>
      {/* Breadcrumb */}
      <nav className="mb-6 flex items-center gap-1.5 font-mono text-xs text-muted-foreground" aria-label="Breadcrumb">
        <Link to="/docs" className="hover:text-foreground">Docs</Link>
        <span aria-hidden>/</span>
        <span className="text-foreground">{meta.title}</span>
      </nav>

      <DocBlocks blocks={content} />

      {/* Prev / next */}
      <div className="mt-12 grid gap-3 border-t border-border pt-6 sm:grid-cols-2">
        {prev ? (
          <Link
            to={`/docs/${prev.slug}`}
            className="group flex flex-col rounded-xl border border-border p-4 transition-colors hover:border-primary/40"
          >
            <span className="inline-flex items-center gap-1 font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
              <ArrowLeft className="h-3.5 w-3.5" /> Previous
            </span>
            <span className="mt-1 font-medium group-hover:text-primary">{prev.title}</span>
          </Link>
        ) : (
          <span />
        )}
        {next && (
          <Link
            to={`/docs/${next.slug}`}
            className="group flex flex-col rounded-xl border border-border p-4 text-right transition-colors hover:border-primary/40 sm:col-start-2"
          >
            <span className="inline-flex items-center justify-end gap-1 font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
              Next <ArrowRight className="h-3.5 w-3.5" />
            </span>
            <span className="mt-1 font-medium group-hover:text-primary">{next.title}</span>
          </Link>
        )}
      </div>
    </article>
  );
}
