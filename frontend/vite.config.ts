import { fileURLToPath, URL } from 'node:url';

import react from '@vitejs/plugin-react';
// From vitest/config, not vite — vite's own defineConfig has no `test` key.
import { defineConfig } from 'vitest/config';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],

  resolve: {
    alias: {
      '@/core': fileURLToPath(new URL('./src/core', import.meta.url)),
      '@/modules': fileURLToPath(new URL('./src/modules', import.meta.url)),
    },
  },

  server: {
    // Loopback only. Vite's default binding would expose the dev server on the
    // LAN, which contradicts the loopback-only threat model the rest of this
    // application is built around.
    host: '127.0.0.1',
    // Must match `build.devUrl` in tauri.conf.json exactly; failing loudly on a
    // taken port beats Tauri pointing at a server that isn't there.
    port: 1420,
    strictPort: true,
  },

  // Tauri's own output has to stay readable alongside Vite's.
  clearScreen: false,

  build: {
    // Windows 11 ships an evergreen WebView2 runtime (verified 150.x on the dev
    // machine), and this is a Windows-only application, so there is no old
    // engine to down-level for. Revisit only if an enterprise fixed-version
    // runtime enters the picture — see README.
    target: 'esnext',
    // Maps are generated but carry no sourceMappingURL comment and are not
    // shipped in the installer. They are archived with the release so a stack
    // captured through /api/v1/client-logs can be symbolicated after the fact.
    sourcemap: 'hidden',
  },

  test: {
    environment: 'node',
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
  },
});
