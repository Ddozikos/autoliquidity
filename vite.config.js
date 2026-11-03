import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';

export default defineConfig({
  root: resolve(import.meta.dirname, 'frontend'),
  plugins: [react()],
  base: '/static/',
  build: {
    outDir: resolve(import.meta.dirname, 'static'),
    emptyOutDir: false,
    assetsDir: 'assets',
  },
  server: {
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
});
