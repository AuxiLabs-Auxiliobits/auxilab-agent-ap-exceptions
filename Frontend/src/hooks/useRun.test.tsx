import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

// Keep the real ApiError / TERMINAL_STATUSES; replace only the `api` object.
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    api: {
      getRun: vi.fn(),
      listRuns: vi.fn(),
    },
  };
});

// Pretend Clerk is loaded and the user is signed in so the provider's effects run.
vi.mock('@clerk/react', () => ({
  useAuth: () => ({ isLoaded: true, isSignedIn: true }),
}));

import { api, ApiError } from '@/lib/api';
import { RunProvider, useRun } from './useRun';

const RUN_ID_KEY = 'ap-active-run-id';

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe('useRun stale-run handling', () => {
  it('clears a stale localStorage run pointer on 404 without surfacing an error', async () => {
    localStorage.setItem(RUN_ID_KEY, 'run_stale');
    vi.mocked(api.listRuns).mockResolvedValue({ runs: [], total: 0 });
    vi.mocked(api.getRun).mockRejectedValue(new ApiError(404, '404 run not found'));

    const { result } = renderHook(() => useRun(), { wrapper: RunProvider });

    await waitFor(() => expect(result.current.runId).toBeNull());
    // The scary global error must NOT be shown — the dashboard falls back to
    // the empty / upload state instead.
    expect(result.current.error).toBeNull();
    expect(localStorage.getItem(RUN_ID_KEY)).toBeNull();
  });
});
