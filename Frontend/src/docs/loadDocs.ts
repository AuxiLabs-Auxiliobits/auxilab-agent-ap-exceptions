import type { Block } from './blocks';
import { DOC_CONTENT } from './content';

/** Look up a documentation page's typed blocks by slug. */
export function getDocBlocks(slug: string): Block[] | null {
  return DOC_CONTENT[slug] ?? null;
}
