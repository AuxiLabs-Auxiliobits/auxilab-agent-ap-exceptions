import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError } from './api';

// Stub Clerk as loaded-but-signed-out so getAuthToken() returns immediately
// (no 5s wait) and requests go out without an Authorization header.
beforeEach(() => {
  (window as unknown as { Clerk?: unknown }).Clerk = { loaded: true, session: null };
});

afterEach(() => {
  vi.restoreAllMocks();
  delete (window as unknown as { Clerk?: unknown }).Clerk;
});

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: String(status),
    json: async () => body,
  } as unknown as Response;
}

describe('api transport', () => {
  it('retries idempotent GETs on a 503 then succeeds', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse(503, { detail: 'unavailable' }))
      .mockResolvedValueOnce(jsonResponse(200, { runs: [], total: 0 }));

    const result = await api.listRuns();
    expect(result).toEqual({ runs: [], total: 0 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('does NOT retry non-idempotent POSTs', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse(503, { detail: 'unavailable' }));

    await expect(api.approveRun('run_1')).rejects.toBeInstanceOf(ApiError);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('maps 401 to a friendly "session expired" message', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(401, { detail: 'no token' }));

    await expect(api.getRun('run_1')).rejects.toMatchObject({
      status: 401,
      message: expect.stringContaining('session has expired'),
    });
  });
});
