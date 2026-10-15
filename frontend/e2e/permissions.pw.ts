import { readFile } from 'node:fs/promises';
import { expect, test, type APIRequestContext } from '@playwright/test';

test.skip(!process.env.TEST_S3_ENDPOINT, 'Permissions browser test requires disposable real storage');

async function mail(request: APIRequestContext, email: string, purpose: string) {
  let link = '';
  await expect.poll(async () => {
    const messages = await (await request.get('http://127.0.0.1:48025/messages')).json() as { to: string; body: string }[];
    link = messages.filter(item => item.to === email && item.body.includes(purpose)).at(-1)?.body.split('\n').find(line => line.startsWith('http'))?.trim() ?? '';
    return link;
  }).not.toBe('');
  return link;
}

test('private ancestors, viewer download, editor rename, and revoked grants protect real files', async ({ page, request, browser }) => {
  test.setTimeout(90000);
  const email = `permission-owner-${Date.now()}@example.com`, memberEmail = `permission-member-${Date.now()}@example.com`;
  const password = 'correct-horse-battery';
  await page.goto('/register'); await page.getByLabel('Full name').fill('Permission Owner');
  await page.getByLabel('Workspace name').fill('Permission Team'); await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Create workspace', exact: true }).click();
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(await mail(request, email, 'purpose=verify'));
  await page.getByRole('button', { name: 'Verify email', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Email verified');
  await page.goto('/app/settings'); await page.getByLabel('Invitation email').fill(memberEmail);
  await page.getByRole('button', { name: 'Create invitation' }).click();
  await expect(page.getByLabel('Private invitation link')).toBeVisible();
  const context = await browser.newContext();
  try {
    const member = await context.newPage(); await member.goto(await mail(request, memberEmail, '/join#token='));
    await member.getByLabel('Full name').fill('Permission Member'); await member.getByLabel('Password', { exact: true }).fill(password);
    await member.getByRole('button', { name: 'Join organization' }).click();
    await expect(member).toHaveURL(/\/app$/); await member.goto(await mail(request, memberEmail, 'purpose=verify'));
    await member.getByRole('button', { name: 'Verify email', exact: true }).click(); await expect(member.getByRole('status')).toContainText('Email verified');
    await page.goto('/app/folders'); await page.getByLabel('Folder name', { exact: true }).fill('Confidential');
    await page.getByRole('button', { name: 'Create folder', exact: true }).click();
    await page.getByRole('button', { name: 'Open folder Confidential' }).click();
    const content = Buffer.from('Real private file with viewer/editor ACL');
    await page.getByLabel('File to upload').setInputFiles({ name: 'Private.txt', mimeType: 'text/plain', buffer: content });
    await page.getByRole('button', { name: 'Upload file', exact: true }).click();
    await expect(page.getByRole('status')).toContainText('File uploaded and verified');
    await page.getByRole('link', { name: 'Permissions for Private.txt' }).click();
    const filePermissionUrl = page.url();
    await page.getByRole('button', { name: 'Make private', exact: true }).click();
    await expect(page.getByRole('status')).toContainText('Resource is private');
    await member.goto('/app/search'); await expect(member.getByText('Private.txt', { exact: true })).toHaveCount(0);
    await page.getByLabel('Workspace member').selectOption({ label: `Permission Member · ${memberEmail}` });
    await page.getByRole('button', { name: 'Save member access' }).click(); await expect(page.getByRole('status')).toContainText('Member access saved');
    await member.reload(); const results = member.getByRole('region', { name: 'Search results' });
    await expect(results.getByText('Private.txt', { exact: true })).toBeVisible();
    await expect(results.getByRole('button', { name: 'Rename file Private.txt' })).toHaveCount(0);
    await expect(results.getByRole('link', { name: 'Permissions for Private.txt' })).toHaveCount(0);
    const event = member.waitForEvent('download'); await results.getByRole('button', { name: 'Download Private.txt' }).click();
    const downloaded = await event; expect(await readFile((await downloaded.path())!)).toEqual(content);
    await page.getByLabel('Resource role').selectOption('editor'); await page.getByRole('button', { name: 'Save member access' }).click();
    await expect(page.getByRole('status')).toContainText('Member access saved'); await member.reload();
    await member.getByRole('button', { name: 'Rename file Private.txt' }).click(); await member.getByLabel('New filename').fill('Edited private.txt');
    await member.getByRole('button', { name: 'Save filename' }).click(); await expect(results.getByText('Edited private.txt', { exact: true })).toBeVisible();
    await page.goto('/app/folders'); await page.getByRole('link', { name: 'Permissions for Confidential' }).click();
    await page.getByRole('button', { name: 'Make private', exact: true }).click(); await expect(page.getByRole('status')).toContainText('Resource is private');
    await member.reload(); await expect(results.getByText('Edited private.txt', { exact: true })).toHaveCount(0);
    await page.getByLabel('Workspace member').selectOption({ label: `Permission Member · ${memberEmail}` });
    await page.getByRole('button', { name: 'Save member access' }).click(); await expect(page.getByRole('status')).toContainText('Member access saved');
    await member.reload(); await expect(results.getByText('Edited private.txt', { exact: true })).toBeVisible();
    await page.goto(filePermissionUrl); await page.getByRole('button', { name: /^Remove access / }).click();
    await expect(page.getByRole('status')).toContainText('Explicit grant removed'); await member.reload();
    await expect(results.getByText('Edited private.txt', { exact: true })).toHaveCount(0);
    await page.setViewportSize({ width: 390, height: 844 }); expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  } finally { await context.close(); }
});
