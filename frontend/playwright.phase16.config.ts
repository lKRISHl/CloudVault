import { defineConfig } from '@playwright/test';

// Only the dedicated Phase 16 journey; no Phase 15 suite or fixture dispatcher.
export default defineConfig({
  testDir: './e2e',
  testMatch: 'phase16.pw.ts',
  workers: 1,
  timeout: 120000,
  expect: { timeout: 30000 },
  use: { baseURL: 'http://127.0.0.1:43916', browserName: 'chromium', headless: true },
});
