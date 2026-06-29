/**
 * Typed content model for the documentation.
 *
 * Pages are authored as `Block[]` in TypeScript (see ./content) and rendered by
 * <DocBlocks> — no Markdown files, no runtime parser. Text fields support a tiny
 * inline syntax (**bold**, `code`, [label](href)) resolved by ./inline.
 *
 * Authoring note: put prose in quoted strings and code samples in `code(...)`
 * template literals. This keeps backtick-heavy code out of prose strings and
 * quote-heavy JSON out of template literals — neither ever needs escaping.
 */
export type Block =
  | { k: 'h'; lvl: 1 | 2 | 3; text: string }
  | { k: 'p'; text: string }
  | { k: 'list'; ordered?: boolean; items: string[] }
  | { k: 'table'; head: string[]; rows: string[][] }
  | { k: 'code'; lang?: string; src: string }
  | { k: 'callout'; tone: 'note' | 'warn' | 'tip'; text: string }
  | { k: 'hr' };

// --- Terse builders so content files read like an outline -------------------
export const h1 = (text: string): Block => ({ k: 'h', lvl: 1, text });
export const h2 = (text: string): Block => ({ k: 'h', lvl: 2, text });
export const h3 = (text: string): Block => ({ k: 'h', lvl: 3, text });
export const p = (text: string): Block => ({ k: 'p', text });
export const ul = (items: string[]): Block => ({ k: 'list', items });
export const ol = (items: string[]): Block => ({ k: 'list', ordered: true, items });
export const table = (head: string[], rows: string[][]): Block => ({ k: 'table', head, rows });
export const code = (lang: string, src: string): Block => ({ k: 'code', lang, src: src.trim() });
export const note = (text: string): Block => ({ k: 'callout', tone: 'note', text });
export const warn = (text: string): Block => ({ k: 'callout', tone: 'warn', text });
export const tip = (text: string): Block => ({ k: 'callout', tone: 'tip', text });
export const hr = (): Block => ({ k: 'hr' });

/** Plain-text extraction (for search indexing of page bodies). */
export function blocksToText(blocks: Block[]): string {
  const strip = (s: string) =>
    s.replace(/\*\*([^*]+)\*\*/g, '$1').replace(/`([^`]+)`/g, '$1').replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
  const out: string[] = [];
  for (const b of blocks) {
    if (b.k === 'h' || b.k === 'p' || b.k === 'callout') out.push(strip(b.text));
    else if (b.k === 'list') out.push(...b.items.map(strip));
    else if (b.k === 'table') out.push(b.head.join(' '), ...b.rows.map((r) => r.map(strip).join(' ')));
    else if (b.k === 'code') out.push(b.src);
  }
  return out.join(' ');
}
