import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { expect, test } from '@playwright/test';

test.skip(!process.env.TEST_S3_ENDPOINT, 'Multipart browser tests require a disposable S3 provider');

test('multipart uploads resume after reload with only missing chunks and can be cancelled', async ({ page, request }) => {
  test.setTimeout(90000);
  const email = `multipart-${Date.now()}@example.com`;
  await page.goto('/register');
  await page.getByLabel('Full name').fill('Multipart Owner');
  await page.getByLabel('Workspace name').fill('Multipart Team');
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill('correct-horse-battery');
  await page.getByRole('button', { name: 'Create workspace', exact: true }).click();
  await expect(page).toHaveURL(/\/app$/);
  let link = '';
  await expect.poll(async () => {
    const messages = await (await request.get('http://127.0.0.1:48025/messages')).json() as { to: string; body: string }[];
    link = messages.filter(mail => mail.to === email && mail.body.includes('purpose=verify')).at(-1)?.body.split('\n').find(line => line.startsWith('http'))?.trim() ?? '';
    return link;
  }).not.toBe('');
  await page.goto(link);
  await page.getByRole('button', { name: 'Verify email', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Email verified');
  await page.goto('/app/folders');
  await page.getByLabel('Use multipart upload').check();
  const body = Buffer.alloc(8 * 1024 * 1024 + 5, 83); body[body.length - 1] = 255;
  const puts: string[] = [];
  page.on('request', outgoing => {
    if (outgoing.method() === 'PUT' && outgoing.url().includes('partNumber=')) {
      expect(outgoing.headers()['authorization']).toBeUndefined();
      expect(outgoing.headers()['cookie']).toBeUndefined();
      expect(outgoing.headers()['referer'] ?? '').toBe('');
      puts.push(outgoing.url());
    }
  });
  await page.getByLabel('File to upload').setInputFiles({ name: 'Parts.bin', mimeType: 'application/octet-stream', buffer: body });
  await page.getByRole('button', { name: 'Upload file', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('File uploaded and verified', { timeout: 30000 });
  expect(puts.length).toBe(2);
  const row = page.getByRole('region', { name: 'Files' }).getByRole('listitem').filter({ hasText: 'Parts.bin' });
  await expect(row).toContainText(`Verified size: ${body.length.toLocaleString('en-US')} bytes`);
  await expect(row).toContainText('Scan complete:', { timeout: 30000 });
  const downloading = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download Parts.bin', exact: true }).click();
  const download = await downloading;
  expect(download.suggestedFilename()).toBe('Parts.bin');
  expect(await download.failure()).toBeNull();
  const downloaded = await readFile((await download.path())!);
  expect(downloaded.length).toBe(body.length);
  expect(createHash('sha256').update(downloaded).digest('hex')).toBe(createHash('sha256').update(body).digest('hex'));
  await page.reload();
  await expect(page.getByText('Parts.bin', { exact: true })).toBeVisible();
  await page.getByLabel('Use multipart upload').check();
  await page.route(`${process.env.TEST_S3_ENDPOINT}/**`, async route => {
    if (route.request().method() === 'PUT' && route.request().url().includes('partNumber=2')) {
      await route.fulfill({ status: 503, headers: { 'Access-Control-Allow-Origin': 'http://127.0.0.1:43000' }, body: 'Simulated provider outage for browser test' });
    } else await route.continue();
  });
  await page.getByLabel('File to upload').setInputFiles({ name: 'Partial.bin', mimeType: 'application/octet-stream', buffer: body });
  await page.getByRole('button', { name: 'Upload file', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Part transfer failed');
  await page.unroute(`${process.env.TEST_S3_ENDPOINT}/**`);
  await page.reload();
  await page.getByRole('button', { name: 'Resume upload Partial.bin', exact: true }).click();
  await expect(page.getByText(/Saved progress: 99%/)).toBeVisible();
  const sentBeforeResume = puts.length;
  const wrong = Buffer.from(body); wrong[0] = 84;
  await page.getByLabel('File to upload').setInputFiles({ name: 'Partial.bin', mimeType: 'application/octet-stream', buffer: wrong });
  await page.getByRole('button', { name: 'Upload file', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('original file content');
  expect(puts.length).toBe(sentBeforeResume);
  await page.getByLabel('File to upload').setInputFiles({ name: 'Partial.bin', mimeType: 'application/octet-stream', buffer: body });
  await page.getByRole('button', { name: 'Upload file', exact: true }).click();
  const resumed = page.getByRole('region', { name: 'Files' }).getByRole('listitem').filter({ hasText: 'Partial.bin' });
  await expect(resumed.getByRole('button', { name: 'Download Partial.bin', exact: true })).toBeVisible();
  expect(puts.length - sentBeforeResume).toBe(1);
  expect(puts.at(-1)).toContain('partNumber=2');
  const resumedDownload = page.waitForEvent('download');
  await expect(resumed).toContainText('Scan complete:', { timeout: 30000 });
  await resumed.getByRole('button', { name: 'Download Partial.bin', exact: true }).click();
  const resumedBytes = await readFile((await (await resumedDownload).path())!);
  expect(createHash('sha256').update(resumedBytes).digest('hex')).toBe(createHash('sha256').update(body).digest('hex'));
  await page.getByLabel('Use multipart upload').check();
  await page.route(`${process.env.TEST_S3_ENDPOINT}/**`, async route => {
    if (route.request().method() === 'PUT' && route.request().url().includes('partNumber=2')) {
      await route.fulfill({ status: 503, headers: { 'Access-Control-Allow-Origin': 'http://127.0.0.1:43000' }, body: 'Provider outage' });
    } else await route.continue();
  });
  await page.getByLabel('File to upload').setInputFiles({ name: 'Cancelled.bin', mimeType: 'application/octet-stream', buffer: body });
  await page.getByRole('button', { name: 'Upload file', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Part transfer failed');
  await page.unroute(`${process.env.TEST_S3_ENDPOINT}/**`);
  await page.getByRole('button', { name: 'Cancel multipart transfer', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Multipart upload cancelled');
  const cancelled = page.getByRole('region', { name: 'Files' }).getByRole('listitem').filter({ hasText: 'Cancelled.bin' });
  await expect(cancelled).toContainText('Cancelled');
  await expect(cancelled.getByRole('button', { name: 'Download Cancelled.bin' })).toHaveCount(0);
});
