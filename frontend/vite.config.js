import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev proxy so the frontend can call the API without CORS friction locally.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': process.env.API_PROXY_TARGET || 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
    globals: true,
  },
});
