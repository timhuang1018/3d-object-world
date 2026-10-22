// One Vite config for every project under samples/. Pick the project with PROJECT (default: the
// first sample). The project folder is the Vite root (its index.html, viewer.html and public/assets),
// and shared engine modules are imported as `@infra/...` from infra/web/.
//
//   npm run dev                                   # samples/scene-001
//   PROJECT=samples/my-scene npm run dev          # another project
import { basename, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

const REPO = fileURLToPath(new URL('.', import.meta.url));
const project = resolve(REPO, process.env.PROJECT || 'samples/scene-001');

export default defineConfig({
  root: project,
  resolve: { alias: { '@infra': resolve(REPO, 'infra/web') } },
  server: { port: 5173, strictPort: true, host: '127.0.0.1', fs: { allow: [REPO] } },
  preview: { port: 4173, strictPort: true, host: '127.0.0.1' },
  build: {
    target: 'es2022',
    outDir: resolve(REPO, 'dist', basename(project)),
    emptyOutDir: true,
    rollupOptions: { input: { main: resolve(project, 'index.html'), viewer: resolve(project, 'viewer.html') } },
  },
});
