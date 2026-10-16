import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e', testMatch: 'phase17.pw.ts', workers: 1, timeout: 60000,
  use: { baseURL: 'http://127.0.0.1:43917', browserName: 'chromium', headless: true },
  webServer: { command: 'npm run dev -- --host 127.0.0.1 --port 43917 --strictPort',
    url: 'http://127.0.0.1:43917', timeout: 30000,
    env: { VITE_API_URL: '', VITE_PROXY_TARGET: 'http://127.0.0.1:48917' } },
});
