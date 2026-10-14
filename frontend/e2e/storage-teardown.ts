/* eslint-env node */
import { spawnSync } from 'node:child_process';

export default function teardown() {
  if (!process.env.TEST_S3_ENDPOINT) return;
  // Playwright can force-stop its Python web server on Windows before finally runs.
  const result = spawnSync('python', ['../scripts/account_e2e_stack.py', '--cleanup-storage'], { stdio: 'inherit' });
  if (result.status !== 0) throw new Error('Disposable browser storage cleanup failed');
}
