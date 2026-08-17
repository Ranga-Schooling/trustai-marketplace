import { afterEach, describe, expect, it, vi } from 'vitest';

import { api, setToken } from './api';

function unauthorizedResponse(detail) {
  return {
    status: 401,
    ok: false,
    json: async () => ({ detail }),
  };
}

describe('API authentication errors', () => {
  afterEach(() => {
    setToken(null);
    vi.unstubAllGlobals();
  });

  it('preserves the API error for an anonymous login failure', async () => {
    setToken(null);
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(unauthorizedResponse('Invalid email or password')),
    );

    await expect(
      api.login({ email: 'buyer@example.com', password: 'wrong-password' }),
    ).rejects.toMatchObject({
      message: 'Invalid email or password',
      status: 401,
    });
  });

  it('reports an expired session when an authenticated request is rejected', async () => {
    setToken('existing-token');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(unauthorizedResponse('Could not validate credentials')),
    );

    await expect(api.me()).rejects.toMatchObject({
      message: 'Your session has expired. Please sign in again.',
      status: 401,
    });
    expect(sessionStorage.getItem('trustai_token')).toBeNull();
  });
});
