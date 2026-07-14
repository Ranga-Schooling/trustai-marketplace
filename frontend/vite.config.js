import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev proxy so the frontend can call the API without CORS friction locally.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:8000' } },
});
