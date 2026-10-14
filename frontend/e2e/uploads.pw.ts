import { readFile } from 'node:fs/promises';
/* eslint-env node */
import { expect, test } from '@playwright/test';

test.skip(!process.env.TEST_S3_ENDPOINT, 'Real upload browser journeys require a disposable S3 test provider');

test('verified user uploads directly to private storage, sees verified size and retains workspace isolation', async ({ page, request }) => {
  const email = `uploads-${Date.now()}@example.com`;
  await page.goto('/register');
  await page.getByLabel('Full name').fill('Upload Owner');
  await page.getByLabel('Workspace name').fill('Upload Team');
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill('correct-horse-battery');
  await page.getByRole('button', { name: 'Create workspace', exact: true }).click();
  await expect(page).toHaveURL(/\/app$/);
  let action = '';
  await expect.poll(async () => {
    const messages = await (await request.get('http://127.0.0.1:48025/messages')).json() as { to: string; body: string }[];
    action = messages.filter((mail) => mail.to === email && mail.body.includes('purpose=verify')).at(-1)?.body.split('\n').find((line) => line.startsWith('http'))?.trim() ?? '';
    return action;
  }).not.toBe('');
  await page.goto(action);
  await page.getByRole('button', { name: 'Verify email', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Email verified');
  await page.goto('/app/folders');
  await page.getByLabel('Folder name', { exact: true }).fill('Documents');
  await page.getByRole('button', { name: 'Create folder', exact: true }).click();
  await page.getByRole('button', { name: 'Open folder Documents' }).click();
  await expect(page.getByRole('navigation', { name: 'Folder breadcrumbs' })).toContainText('Documents');
  const content = Buffer.from('Actual Chromium presigned upload.');
  let storageReceivedBearer = false;
  let transferred = false;
  page.on('request', (outgoing) => {
    if (outgoing.method() === 'PUT' && outgoing.url().includes('/tenants/')) {
      transferred = true;
      storageReceivedBearer = !!outgoing.headers()['authorization'] || !!outgoing.headers()['cookie'];
    }
  });
  const picker = page.getByLabel('File to upload');
  await expect(picker).toBeEnabled();
  await picker.setInputFiles({ name: 'Browser.txt', mimeType: 'text/plain', buffer: content });
  await page.getByRole('button', { name: 'Upload file', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('File uploaded and verified');
  const row = page.getByRole('region', { name: 'Files' }).getByRole('listitem').filter({ hasText: 'Browser.txt' });
  await expect(row).toContainText(`Uploaded · Verified size: ${content.length} bytes`);
  expect(storageReceivedBearer).toBe(false);
  expect(transferred).toBe(true);
  let downloadWithoutCredentials = false;
  page.on('request', outgoing => {
    if (outgoing.method() === 'GET' && outgoing.url().includes('/tenants/')) {
      downloadWithoutCredentials = !outgoing.headers()['authorization'] && !outgoing.headers()['cookie'] && !outgoing.headers()['referer'];
    }
  });
  const downloadEvent = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download Browser.txt', exact: true }).click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe('Browser.txt');
  expect(await download.failure()).toBeNull();
  const saved = await download.path();
  expect(await readFile(saved!)).toEqual(content);
  expect(downloadWithoutCredentials).toBe(true);
  await page.reload();
  await expect(page.getByText('Browser.txt', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'All folders', exact: true }).click();
  await expect(page.getByText('Browser.txt', { exact: true })).toHaveCount(0);
  await page.getByRole('link', { name: 'Back to workspace' }).click();
  await page.getByLabel('New workspace name').fill('Other Upload Team');
  await page.getByRole('button', { name: 'Create another workspace' }).click();
  await expect(page.getByText('Current workspace: Other Upload Team', { exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Browse folders' }).click();
  await expect(page.getByText('No file metadata here.', { exact: true })).toBeVisible();
});
