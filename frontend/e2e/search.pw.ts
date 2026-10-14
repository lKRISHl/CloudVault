import { randomUUID, createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { expect, test } from '@playwright/test';

test.skip(!process.env.TEST_S3_ENDPOINT, 'Search browser test requires disposable real storage');

test('filename search filters, pages, downloads and isolates switched workspaces', async ({ page, request }) => {
  test.setTimeout(90000);
  const email = `search-${Date.now()}@example.com`;
  await page.goto('/register');
  await page.getByLabel('Full name').fill('Search Owner');
  await page.getByLabel('Workspace name').fill('Search Team');
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill('correct-horse-battery');
  const registered = page.waitForResponse(response => response.url().endsWith('/auth/register') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Create workspace', exact: true }).click();
  const session = await (await registered).json() as { access_token: string };
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
  await page.getByLabel('Folder name', { exact: true }).fill('Reports');
  await page.getByRole('button', { name: 'Create folder', exact: true }).click();
  await page.getByRole('button', { name: 'Open folder Reports', exact: true }).click();
  await expect(page.getByRole('navigation', { name: 'Folder breadcrumbs' })).toContainText('Reports');
  const content = Buffer.from('Search result download verified');
  await page.getByLabel('File to upload').setInputFiles({ name: 'Résumé 50%.txt', mimeType: 'text/plain', buffer: content });
  await page.getByRole('button', { name: 'Upload file', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('File uploaded and verified');
  const headers = { Authorization: `Bearer ${session.access_token}` };
  const checksum = createHash('sha256').update(content).digest('base64');
  for (let index = 0; index < 5; index++) {
    const reserved = await request.post('/api/v1/files/uploads', { headers, data: {
      name: `Pending-${index}.txt`, declared_size_bytes: content.length, declared_content_type: 'text/plain',
      checksum_sha256: checksum, request_id: randomUUID(),
    } });
    expect(reserved.status()).toBe(201);
  }
  await page.getByRole('link', { name: 'Search this folder', exact: true }).click();
  await expect(page.getByLabel('Search scope')).toHaveValue('folder');
  const results = page.getByRole('region', { name: 'Search results' });
  await expect(results.getByText('Résumé 50%.txt', { exact: true })).toBeVisible();
  await page.getByLabel('Filename', { exact: true }).fill('50%');
  await page.getByLabel('Upload status').selectOption('uploaded');
  await page.getByRole('button', { name: 'Search files', exact: true }).click();
  await expect(results.getByRole('listitem')).toHaveCount(1);
  const downloadEvent = page.waitForEvent('download');
  await results.getByRole('button', { name: 'Download Résumé 50%.txt', exact: true }).click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe('Résumé 50%.txt');
  expect(await readFile((await download.path())!)).toEqual(content);
  await page.getByRole('button', { name: 'Clear filters', exact: true }).click();
  await page.getByLabel('Results per page').selectOption('5');
  await page.getByLabel('Sort direction').selectOption('desc');
  await page.getByRole('button', { name: 'Search files', exact: true }).click();
  await expect(results.getByRole('listitem')).toHaveCount(5);
  await page.getByRole('button', { name: 'Next results', exact: true }).click();
  await expect(results.getByRole('listitem')).toHaveCount(1);
  await expect(results.getByText('Pending-0.txt', { exact: true })).toBeVisible();
  await page.getByLabel('Filename', { exact: true }).fill('absent');
  await page.getByRole('button', { name: 'Search files', exact: true }).click();
  await expect(results.getByRole('listitem')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Previous results' })).toBeDisabled();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.goto('/app');
  await page.getByLabel('New workspace name').fill('Other Search Workspace');
  await page.getByRole('button', { name: 'Create another workspace', exact: true }).click();
  await expect(page.getByText('Current workspace: Other Search Workspace', { exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Search files', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Search results' }).getByRole('listitem')).toHaveCount(0);
  await expect(page.getByText('Résumé 50%.txt', { exact: true })).toHaveCount(0);
});
