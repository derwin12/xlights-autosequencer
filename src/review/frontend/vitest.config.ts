import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  define: {
    // Build-stamp constants injected by vite.config.ts at build time.
    // vitest uses this separate config, so they must be defined here too
    // or any component rendering the header stamp crashes under jsdom.
    __BUILD_TIME__: JSON.stringify('1970-01-01T00:00:00.000Z'),
    __GIT_COMMIT__: JSON.stringify('test'),
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    globals: true,
    exclude: ['tests/e2e/**', 'node_modules/**'],
  },
  resolve: {
    alias: {
      src: '/workspace/src/review/frontend/src',
    },
  },
});
