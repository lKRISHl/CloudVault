import { readFile } from 'node:fs/promises';
import { expect, test } from '@playwright/test';

test.skip(!process.env.TEST_S3_ENDPOINT, 'Recovery browser test requires disposable real storage');

test('file movement, renamed recovery and confirmed folder upload cancellation work with real storage', async ({ page, request }) => {
  test.setTimeout(90000);
  const email = `recovery-${Date.now()}@example.com`;
  await page.goto('/register');
  await page.getByLabel('Full name').fill('Recovery Owner');
  await page.getByLabel('Workspace name').fill('Recovery Team');
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill('correct-horse-battery');
  await page.getByRole('button', { name: 'Create workspace', exact: true }).click();
  await expect(page).toHaveURL(/\/app$/);
  let link = '';
  await expect.poll(async () => {
    const messages = await (await request.get('http://127.0.0.1:48025/messages')).json() as { to: string; body: string }[];
    link = messages.filter(item => item.to === email && item.body.includes('purpose=verify')).at(-1)?.body.split('\n').find(line => line.startsWith('http'))?.trim() ?? '';
    return link;
  }).not.toBe('');
  await page.goto(link); await page.getByRole('button', { name: 'Verify email', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Email verified');
  await page.goto('/app/folders');
  await page.getByLabel('Folder name', { exact: true }).fill('Destination');
  await page.getByRole('button', { name: 'Create folder', exact: true }).click();
  const body = Buffer.from('Unchanged bytes after move and recovery');
  await page.getByLabel('File to upload').setInputFiles({ name: 'Move.txt', mimeType: 'text/plain', buffer: body });
  await page.getByRole('button', { name: 'Upload file', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'File uploaded and verified' })).toBeVisible();
  await page.getByRole('button', { name: 'Move Move.txt', exact: true }).click();
  await page.getByRole('button', { name: 'Open destination Destination', exact: true }).click();
  await page.getByRole('button', { name: 'Move here', exact: true }).click();
  await expect(page.getByText('Move.txt', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Open folder Destination', exact: true }).click();
  await expect(page.getByText('Move.txt', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Move Move.txt to trash', exact: true }).click();
  await page.getByRole('link', { name: 'Trash', exact: true }).click();
  await page.getByRole('button', { name: 'Restore elsewhere Move.txt', exact: true }).click();
  await page.getByLabel('Restored name').fill('Recovered.txt');
  await page.getByRole('button', { name: 'Restore here', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('original permissions');
  await page.getByRole('link', { name: 'Back to files', exact: true }).click();
  const event = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download Recovered.txt', exact: true }).click();
  expect(await readFile((await (await event).path())!)).toEqual(body);
  await page.getByRole('button', { name: 'Open folder Destination', exact: true }).click();
  await expect(page).toHaveURL(/folder=/);
  await expect(page.getByRole('navigation', { name: 'Folder breadcrumbs' }).getByRole('button', { name: 'Destination', exact: true })).toBeVisible();
  await page.route('http://127.0.0.1:9000/**', async route => {
    if (route.request().method() === 'PUT') await route.abort('failed'); else await route.continue();
  });
  // The isolated stack signs to the configured localhost storage endpoint.
  await page.route('http://localhost:9000/**', async route => {
    if (route.request().method() === 'PUT') await route.abort('failed'); else await route.continue();
  });
  await page.getByLabel('File to upload').setInputFiles({ name: 'Pending.txt', mimeType: 'text/plain', buffer: Buffer.from('interrupted') });
  await page.getByRole('button', { name: 'Upload file', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Retry upload Pending.txt', exact: true })).toBeVisible();
  await page.goto('/app/folders');
  await page.getByRole('button', { name: 'Cancel uploads and trash Destination', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Confirm cancellation and trash' })).toBeDisabled();
  await page.getByLabel('Type CANCEL UPLOADS to continue').fill('CANCEL UPLOADS');
  await page.getByRole('button', { name: 'Confirm cancellation and trash', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Open folder Destination', exact: true })).toHaveCount(0);
  await page.getByRole('link', { name: 'Trash', exact: true }).click();
  await page.getByRole('button', { name: 'Restore Destination', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('original permissions');
  await page.getByRole('link', { name: 'Back to files', exact: true }).click();
  await page.getByRole('button', { name: 'Open folder Destination', exact: true }).click();
  await expect(page.getByText('Upload cancelled. Outstanding transfers are cleaned after their original authorization deadline.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Retry upload Pending.txt', exact: true })).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});
