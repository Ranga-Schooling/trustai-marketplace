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

describe('Visual Inspection API requests', () => {
  afterEach(() => {
    setToken(null);
    vi.unstubAllGlobals();
  });

  it('posts every selected photo under the repeated photos field without setting multipart Content-Type', async () => {
    setToken('existing-token');
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({ findings: [] }),
    });
    vi.stubGlobal('fetch', fetchMock);
    const files = [
      new File(['jpeg'], 'front.jpg', { type: 'image/jpeg' }),
      new File(['png'], 'back.png', { type: 'image/png' }),
      new File(['webp'], 'label.webp', { type: 'image/webp' }),
    ];

    await api.visualInspect(42, files);

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/analyses/42/visual-inspection');
    expect(options.method).toBe('POST');
    expect(options.body).toBeInstanceOf(FormData);
    expect(options.body.getAll('photos')).toEqual(files);
    expect(options.headers.Authorization).toBe('Bearer existing-token');
    expect(
      Object.keys(options.headers).some((header) => header.toLowerCase() === 'content-type'),
    ).toBe(false);
  });

  it('preserves JSON Content-Type for existing JSON requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      status: 200,
      ok: true,
      json: async () => ({ access_token: 'new-token' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    await api.login({ email: 'buyer@example.com', password: 'safe-password' });

    expect(fetchMock.mock.calls[0][1].headers['Content-Type']).toBe('application/json');
  });
});
