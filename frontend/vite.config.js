import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev proxy so the frontend can call the API without CORS friction locally.
// Target is overridable via API_PROXY_TARGET: the backend is reachable at
// localhost:8000 when running the frontend directly, but at the `api`
// service name when running inside Docker Compose.
const apiProxyTarget = process.env.API_PROXY_TARGET || 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    proxy: { '/api': apiProxyTarget },
  },
});
