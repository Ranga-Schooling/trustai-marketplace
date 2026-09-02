// Minimal API client. VITE_API_BASE lets the deployed frontend point at the
// Render backend; empty string uses the Vite dev proxy locally.
const BASE = import.meta.env.VITE_API_BASE || '';

let token = sessionStorage.getItem('trustai_token') || null;

export function setToken(t) {
  token = t;
  if (t) sessionStorage.setItem('trustai_token', t);
  else sessionStorage.removeItem('trustai_token');
}

export function hasToken() {
  return Boolean(token);
}

// Lets the app react when a request discovers the session is no longer
// valid (401 on a request that did carry a token) -- registered once by
// App.jsx so React state (`user`) gets reset at the same time the token
// does, instead of only on the boot-time check. Without this, a 401 hit
// on an already-mounted authenticated screen clears the token but leaves
// the UI looking signed in, so a retry goes out with no token at all and
// shows the raw backend error instead of the friendly message below.
let onSessionExpired = null;

export function setOnSessionExpired(fn) {
  onSessionExpired = fn;
}

async function request(path, options = {}) {
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
  const headers = {
    ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...(options.headers || {}),
  };
  const hadToken = hasToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${BASE}/api${path}`, { ...options, headers });
  if (res.status === 401 && hadToken) {
    setToken(null);
    onSessionExpired?.();
    throw new ApiError('Your session has expired. Please sign in again.', 401);
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail =
      typeof body.detail === 'string'
        ? body.detail
        : 'Something went wrong. Please check your input and try again.';
    throw new ApiError(detail, res.status);
  }
  return body;
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export const api = {
  register: (data) => request('/auth/register', { method: 'POST', body: JSON.stringify(data) }),
  login: (data) => request('/auth/login', { method: 'POST', body: JSON.stringify(data) }),
  me: () => request('/auth/me'),
  updateMe: (data) => request('/auth/me', { method: 'PATCH', body: JSON.stringify(data) }),
  deleteMe: () => request('/auth/me', { method: 'DELETE' }),
  createAnalysis: (data) => request('/analyses', { method: 'POST', body: JSON.stringify(data) }),
  previewListingUrl: (url) => request('/listings/preview', { method: 'POST', body: JSON.stringify({ url }) }),
  listAnalyses: () => request('/analyses'),
  getAnalysis: (id) => request(`/analyses/${id}`),
  visualInspect: (analysisId, files) => {
    const body = new FormData();
    files.forEach((file) => body.append('photos', file));
    return request(`/analyses/${analysisId}/visual-inspection`, { method: 'POST', body });
  },
};
