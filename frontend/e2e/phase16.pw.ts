import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';

test('real Celery queued poster, cancellation and retry work through the browser', async ({ page, request }) => {
  const manifest = JSON.parse(readFileSync('../.local/phase16-stack.json', 'utf8')) as { project: string };
  if (!/^cv-phase16-check-[0-9a-f]{12}$/.test(manifest.project)) throw Error('Unowned stack');
  const video = execFileSync('docker', ['compose', '-p', manifest.project, '-f', '../docker-compose.yml',
    '-f', '../infra/testing/phase16.compose.yml', 'exec', '-T', 'preview-renderer',
    'ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=80x40:d=1', '-c:v', 'libx264',
    '-threads', '1', '-pix_fmt', 'yuv420p', '-movflags', 'frag_keyframe+empty_moov', '-f', 'mp4', 'pipe:1']);
  const email = `queue-browser-${Date.now()}@example.com`;
  await page.goto('/register');
  await page.getByLabel('Full name').fill('Queue Owner');
  await page.getByLabel('Workspace name').fill('Queue Browser');
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill('correct-horse-battery');
  await page.getByRole('button', { name: 'Create workspace', exact: true }).click();
  await expect(page).toHaveURL(/\/app$/);
  let link = '';
  await expect.poll(async () => {
    const data = await (await request.get('http://127.0.0.1:48916/api/v1/search', { params: { query: `to:${email}` } })).json();
    for (const message of data.messages ?? []) {
      const mail = await (await request.get(`http://127.0.0.1:48916/api/v1/message/${message.ID}`)).json();
      link = mail.Text.split('\n').find((line: string) => line.startsWith('http') && line.includes('purpose=verify'))?.trim() ?? '';
    }
    return link;
  }).not.toBe('');
  await page.goto(link);
  await page.getByRole('button', { name: 'Verify email', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Email verified');
  await page.goto('/app/folders');
  await page.getByLabel('File to upload').setInputFiles({ name: 'Queue poster.mp4', mimeType: 'video/mp4', buffer: video });
  await page.getByRole('button', { name: 'Upload file', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'File uploaded and verified' })).toBeVisible();
  const compose = (...args: string[]) => execFileSync('docker', ['compose', '-p', manifest.project,
    '-f', '../docker-compose.yml', '-f', '../infra/testing/phase16.compose.yml', ...args]);
  // A stopped real worker keeps the request queued without mocking browser responses.
  compose('stop', 'preview-worker');
  try {
    const firstPoll = page.waitForResponse(response => response.request().method() === 'GET' && /\/preview-jobs\//.test(response.url()));
    await page.getByRole('link', { name: 'Preview Queue poster.mp4', exact: true }).click();
    expect((await (await firstPoll).json()).state).toBe('queued');
    const cancelled = page.waitForResponse(response => response.request().method() === 'DELETE' && response.url().includes('/preview-jobs/'));
    await page.getByRole('button', { name: 'Cancel preview', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('Preview cancelled');
    expect((await cancelled).status()).toBe(200);
  } finally {
    compose('up', '-d', '--no-deps', 'preview-worker');
  }
  await page.getByRole('button', { name: 'Refresh preview', exact: true }).click();
  await expect(page.getByText('Static video poster.', { exact: false })).toBeVisible();
  await expect(page.getByRole('img')).toHaveAttribute('src', /^blob:/);
  await expect(page.locator('main video, main iframe, main object, main embed')).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});
