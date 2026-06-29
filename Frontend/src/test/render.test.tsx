import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

// Smoke test proving the jsdom + Testing Library + jest-dom setup works, so the
// vitest `environment: 'jsdom'` switch is exercised in CI.
describe('test environment', () => {
  it('renders a React element into the DOM', () => {
    render(<button type="button">Approve run</button>);
    expect(screen.getByRole('button', { name: 'Approve run' })).toBeInTheDocument();
  });
});
