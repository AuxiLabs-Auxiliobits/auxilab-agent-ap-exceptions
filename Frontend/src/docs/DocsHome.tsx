import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { DOC_GROUPS } from './manifest';
import { SearchTrigger } from './DocsSearch';

/** The /docs landing: title + search + an "Explore by Category" card grid. */
export function DocsHome() {
  return (
    <div>
      {/* Breadcrumb */}
      <nav className="mb-5 flex items-center gap-1.5 font-mono text-xs text-muted-foreground" aria-label="Breadcrumb">
        <Link to="/docs" className="hover:text-foreground">Docs</Link>
        <span aria-hidden>/</span>
        <span className="text-foreground">Overview</span>
      </nav>

      <h1 className="font-display text-4xl font-semibold tracking-tight">Documentation</h1>
      <p className="mt-3 max-w-2xl text-lg text-muted-foreground">
        Complete guides and resources for the AP Exception Agent — upload an exception queue,
        understand how invoices are classified and routed, integrate with the API, and run the
        platform in production.
      </p>

      <div className="mt-7 max-w-2xl">
        <SearchTrigger big className="w-full" />
      </div>

      <h2 className="mb-5 mt-12 font-display text-xl font-semibold tracking-tight">Explore by Category</h2>
      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
        {DOC_GROUPS.map((g) => {
          const Icon = g.icon;
          const first = g.pages[0];
          return (
            <div
              key={g.title}
              className="flex flex-col rounded-2xl border border-border bg-card p-6 transition-all hover:border-primary/40 hover:shadow-sm"
            >
              <span className="grid h-11 w-11 place-items-center rounded-xl bg-primary/10 ring-1 ring-primary/15">
                <Icon className="h-5 w-5 text-primary" aria-hidden />
              </span>
              <h3 className="mt-4 font-display text-lg font-semibold tracking-tight">{g.title}</h3>
              <p className="mt-1.5 flex-1 text-sm leading-relaxed text-muted-foreground">{g.blurb}</p>
              <Link
                to={`/docs/${first.slug}`}
                className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:gap-2"
              >
                View Guides <ArrowRight className="h-4 w-4 transition-all" />
              </Link>
            </div>
          );
        })}
      </div>
    </div>
  );
}
