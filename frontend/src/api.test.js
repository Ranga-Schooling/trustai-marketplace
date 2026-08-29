import { afterEach, describe, expect, it, vi } from 'vitest';

import { api, setOnSessionExpired, setToken } from './api';

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
    setOnSessionExpired(null);
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

  it('notifies the registered session-expired handler on an authenticated 401', async () => {
    setToken('existing-token');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(unauthorizedResponse('Could not validate credentials')),
    );
    const onSessionExpired = vi.fn();
    setOnSessionExpired(onSessionExpired);

    await expect(api.me()).rejects.toBeTruthy();

    expect(onSessionExpired).toHaveBeenCalledTimes(1);
  });

  it('does not notify the session-expired handler for an anonymous login failure', async () => {
    setToken(null);
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(unauthorizedResponse('Invalid email or password')),
    );
    const onSessionExpired = vi.fn();
    setOnSessionExpired(onSessionExpired);

    await expect(
      api.login({ email: 'buyer@example.com', password: 'wrong-password' }),
    ).rejects.toBeTruthy();

    expect(onSessionExpired).not.toHaveBeenCalled();
  });
});
