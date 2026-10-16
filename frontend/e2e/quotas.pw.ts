import { expect, test } from '@playwright/test';

test.skip(!process.env.TEST_S3_ENDPOINT || process.env.TEST_QUOTA_ZERO_LIMIT !== '1',
  'Run separately with disposable storage and STORAGE_FREE_LIMIT_BYTES=0');

test('zero-quota admission is visible and creates no file or provider transfer', async ({ page, request }) => {
  const email = `quota-browser-${Date.now()}@example.com`;
  await page.goto('/register');
  await page.getByLabel('Full name').fill('Quota Owner');
  await page.getByLabel('Workspace name').fill('Quota Workspace');
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill('correct-horse-battery');
  await page.getByRole('button', { name: 'Create workspace', exact: true }).click();
  await expect(page).toHaveURL(/\/app$/);
  let link = '';
  await expect.poll(async () => {
    const mails = await (await request.get('http://127.0.0.1:48025/messages')).json() as { to: string; body: string }[];
    link = mails.filter(mail => mail.to === email).at(-1)?.body.split('\n').find(line => line.startsWith('http'))?.trim() ?? '';
    return link;
  }).not.toBe('');
  await page.goto(link);
  await page.getByRole('button', { name: 'Verify email', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Email verified');
  await page.goto('/app/settings');
  await expect(page.getByLabel('Workspace storage')).toContainText('of 0 MiB');
  await page.goto('/app/folders');
  let providerTransfer = false;
  page.on('request', outgoing => {
    if (outgoing.method() === 'PUT' && outgoing.url().includes('/tenants/')) providerTransfer = true;
  });
  await page.getByLabel('File to upload').setInputFiles({
    name: 'Denied.txt', mimeType: 'text/plain', buffer: Buffer.from('not admitted'),
  });
  await page.getByRole('button', { name: 'Upload file', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Workspace storage quota exceeded');
  expect(providerTransfer).toBe(false);
  await expect(page.getByRole('region', { name: 'Files' }).getByRole('listitem')
    .filter({ hasText: 'Denied.txt' })).toHaveCount(0);
  await page.goto('/app/settings');
  await expect(page.getByLabel('Workspace storage')).toContainText('Free allocation: 0 MiB of 0 MiB');
});
