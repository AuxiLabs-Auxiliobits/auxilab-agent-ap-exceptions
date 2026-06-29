import { Info, AlertTriangle, Lightbulb } from 'lucide-react';
import type { Block } from './blocks';
import { renderInline } from './inline';

/** Renders a typed documentation page (Block[]) as themed React UI. */
export function DocBlocks({ blocks }: { blocks: Block[] }) {
  return (
    <div className="text-[15px] leading-7 text-foreground/90">
      {blocks.map((b, i) => (
        <BlockView key={i} block={b} />
      ))}
    </div>
  );
}

const CALLOUT = {
  note: { icon: Info, ring: 'border-primary/50 bg-primary/[0.06]', tint: 'text-primary' },
  warn: { icon: AlertTriangle, ring: 'border-pending/50 bg-pending/[0.07]', tint: 'text-pending' },
  tip: { icon: Lightbulb, ring: 'border-settled/50 bg-settled/[0.07]', tint: 'text-settled' },
} as const;

function BlockView({ block }: { block: Block }) {
  switch (block.k) {
    case 'h':
      if (block.lvl === 1)
        return (
          <h1 className="mb-4 mt-1 scroll-mt-24 font-display text-3xl font-semibold tracking-tight text-foreground">
            {renderInline(block.text)}
          </h1>
        );
      if (block.lvl === 2)
        return (
          <h2 className="mb-3 mt-10 scroll-mt-24 border-b border-border pb-2 font-display text-xl font-semibold tracking-tight text-foreground">
            {renderInline(block.text)}
          </h2>
        );
      return (
        <h3 className="mb-2 mt-7 scroll-mt-24 text-base font-semibold text-foreground">
          {renderInline(block.text)}
        </h3>
      );

    case 'p':
      return <p className="my-4">{renderInline(block.text)}</p>;

    case 'list': {
      const cls = 'my-4 ml-5 space-y-1.5 marker:text-muted-foreground';
      const items = block.items.map((it, i) => (
        <li key={i} className="pl-1">
          {renderInline(it)}
        </li>
      ));
      return block.ordered ? (
        <ol className={`list-decimal ${cls}`}>{items}</ol>
      ) : (
        <ul className={`list-disc ${cls}`}>{items}</ul>
      );
    }

    case 'table':
      return (
        <div className="my-5 overflow-x-auto rounded-xl border border-border">
          <table className="w-full border-collapse text-sm">
            <thead className="bg-muted/60">
              <tr>
                {block.head.map((h, i) => (
                  <th key={i} className="border-b border-border px-3 py-2 text-left font-semibold text-foreground">
                    {renderInline(h)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, r) => (
                <tr key={r}>
                  {row.map((cell, c) => (
                    <td
                      key={c}
                      className="border-b border-border px-3 py-2 align-top text-foreground/85 [&_code]:whitespace-nowrap"
                    >
                      {renderInline(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );

    case 'code':
      return (
        <pre className="my-5 overflow-x-auto rounded-xl border border-border bg-muted/60 p-4">
          <code className="font-mono text-[13px] text-foreground">{block.src}</code>
        </pre>
      );

    case 'callout': {
      const c = CALLOUT[block.tone];
      const Icon = c.icon;
      return (
        <div className={`my-5 flex gap-3 rounded-lg border-l-4 px-4 py-3 ${c.ring}`}>
          <Icon className={`mt-0.5 h-[18px] w-[18px] shrink-0 ${c.tint}`} aria-hidden />
          <p className="text-foreground/90">{renderInline(block.text)}</p>
        </div>
      );
    }

    case 'hr':
      return <hr className="my-8 border-border" />;
  }
}
