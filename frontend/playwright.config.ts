/* eslint-env node */
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testMatch: '**/*.pw.ts',
  workers: 1,
  timeout: 45000,
  use: { baseURL: 'http://127.0.0.1:43000', browserName: 'chromium', headless: true },
  webServer: [
    { command: 'python ../scripts/account_e2e_stack.py', url: 'http://127.0.0.1:48000/api/v1/health', timeout: 60000 },
    { command: 'npm run dev -- --host 127.0.0.1 --port 43000 --strictPort', url: 'http://127.0.0.1:43000',
      env: { VITE_API_URL: '', VITE_PROXY_TARGET: 'http://127.0.0.1:48000' }, timeout: 60000 },
  ],
});
