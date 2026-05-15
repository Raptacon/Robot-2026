import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { fileURLToPath } from 'node:url';

const here = fileURLToPath(new URL('.', import.meta.url));

// Build straight into the Python server's static/ directory so
// `python -m host.controller_web_editor` serves the SPA without extra wiring.
export default defineConfig({
  plugins: [svelte()],
  build: {
    outDir: `${here}/../static`,
    emptyOutDir: true,
    // Source maps inflate the git-tracked build by ~700KB and aren't
    // useful for end users.  Run `vite dev` (proxy to :8071) for
    // SPA debugging instead.
    sourcemap: false,
  },
  server: {
    port: 5173,
    // During `vite dev` the API still lives on the Python server.
    proxy: {
      '/api': 'http://127.0.0.1:8071',
    },
  },
});
