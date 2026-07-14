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

async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${BASE}/api${path}`, { ...options, headers });
  if (res.status === 401) {
    setToken(null);
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
  createAnalysis: (data) => request('/analyses', { method: 'POST', body: JSON.stringify(data) }),
  listAnalyses: () => request('/analyses'),
  getAnalysis: (id) => request(`/analyses/${id}`),
};
