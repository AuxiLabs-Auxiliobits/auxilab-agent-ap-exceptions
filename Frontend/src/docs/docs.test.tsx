import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { DocsPage } from './DocsPage';
import { ALL_DOC_PAGES } from './manifest';
import { getDocBlocks } from './loadDocs';

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/docs/:slug" element={<DocsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('docs', () => {
  it('every manifest page has matching typed content', () => {
    for (const page of ALL_DOC_PAGES) {
      const blocks = getDocBlocks(page.slug);
      expect(blocks, `missing content for ${page.slug}`).toBeTruthy();
      expect(blocks!.length, `empty content for ${page.slug}`).toBeGreaterThan(0);
    }
  });

  it('renders a known page as a heading', () => {
    renderAt('/docs/api-reference');
    expect(screen.getByRole('heading', { level: 1, name: /API Reference/i })).toBeInTheDocument();
  });

  it('shows a 404 for an unknown page', () => {
    renderAt('/docs/does-not-exist');
    expect(screen.getByText('404')).toBeInTheDocument();
  });
});
