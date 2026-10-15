import { readFile } from 'node:fs/promises';
import { expect, test } from '@playwright/test';

test.skip(!process.env.TEST_S3_ENDPOINT, 'Version browser test requires disposable real storage');

test('real replacement and historical downloads retain both contents and restore the current version', async ({ page, request }) => {
  test.setTimeout(90000);
  const email = `versions-${Date.now()}@example.com`;
  await page.goto('/register'); await page.getByLabel('Full name').fill('Version Owner');
  await page.getByLabel('Workspace name').fill('Version Team'); await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill('correct-horse-battery');
  await page.getByRole('button', { name: 'Create workspace', exact: true }).click(); await expect(page).toHaveURL(/\/app$/);
  let link = '';
  await expect.poll(async () => {
    const messages = await (await request.get('http://127.0.0.1:48025/messages')).json() as { to: string; body: string }[];
    link = messages.filter(item => item.to === email && item.body.includes('purpose=verify')).at(-1)?.body.split('\n').find(line => line.startsWith('http'))?.trim() ?? '';
    return link;
  }).not.toBe('');
  await page.goto(link); await page.getByRole('button', { name: 'Verify email', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Email verified'); await page.goto('/app/folders');
  const original = Buffer.from('Original browser version bytes'); const updated = Buffer.from('Replacement browser bytes');
  await page.getByLabel('File to upload').setInputFiles({ name: 'Versioned.txt', mimeType: 'text/plain', buffer: original });
  await page.getByRole('button', { name: 'Upload file', exact: true }).click(); await expect(page.getByRole('status')).toContainText('File uploaded and verified');
  await page.getByRole('link', { name: 'Versions of Versioned.txt', exact: true }).click();
  await expect(page.getByText('Current: version 1', { exact: true })).toBeVisible();
  await page.getByLabel('Replacement file', { exact: true }).setInputFiles({ name: 'Different name.txt', mimeType: 'text/plain', buffer: updated });
  await page.getByRole('button', { name: 'Upload new version', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Version uploaded and verified');
  await expect(page.getByText('Current: version 2', { exact: true })).toBeVisible();
  for (const [number, bytes] of [[1, original], [2, updated]] as const) {
    const event = page.waitForEvent('download'); await page.getByRole('button', { name: `Download version ${number}`, exact: true }).click();
    const downloaded = await event; expect(await readFile((await downloaded.path())!)).toEqual(bytes);
    expect(downloaded.suggestedFilename()).toBe('Versioned.txt');
  }
  await page.getByRole('button', { name: 'Restore version 1', exact: true }).click();
  await page.getByRole('button', { name: 'Confirm restore', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Version restored');
  await expect(page.getByText('Current: version 1', { exact: true })).toBeVisible();
  await page.reload(); await expect(page.getByText('Current: version 1', { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.getByRole('link', { name: 'Back to files', exact: true }).click();
  const event = page.waitForEvent('download'); await page.getByRole('button', { name: 'Download Versioned.txt', exact: true }).click();
  expect(await readFile((await (await event).path())!)).toEqual(original);
});

test('multipart replacement resumes after reload, supports cancellation and protects current history from pruning', async ({ page, request }) => {
  test.setTimeout(120000);
  const email = `version-resume-${Date.now()}@example.com`;
  await page.goto('/register'); await page.getByLabel('Full name').fill('Resume Owner');
  await page.getByLabel('Workspace name').fill('Resume Team'); await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill('correct-horse-battery');
  await page.getByRole('button', { name: 'Create workspace', exact: true }).click(); await expect(page).toHaveURL(/\/app$/);
  let link = '';
  await expect.poll(async () => {
    const messages = await (await request.get('http://127.0.0.1:48025/messages')).json() as { to: string; body: string }[];
    link = messages.filter(item => item.to === email && item.body.includes('purpose=verify')).at(-1)?.body.split('\n').find(line => line.startsWith('http'))?.trim() ?? '';
    return link;
  }).not.toBe('');
  await page.goto(link); await page.getByRole('button', { name: 'Verify email', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Email verified'); await page.goto('/app/folders');
  await page.getByLabel('File to upload').setInputFiles({ name: 'Resume history.bin', mimeType: 'application/octet-stream', buffer: Buffer.from('original') });
  await page.getByRole('button', { name: 'Upload file', exact: true }).click(); await expect(page.getByRole('status')).toContainText('File uploaded and verified');
  await page.getByRole('link', { name: 'Versions of Resume history.bin', exact: true }).click();
  await expect(page.getByText('Current: version 1', { exact: true })).toBeVisible();
  const body = Buffer.alloc(8 * 1024 * 1024 + 5, 86);
  let puts = 0;
  page.on('request', outgoing => { if (outgoing.method() === 'PUT' && outgoing.url().includes('partNumber=')) {
    puts++; expect(outgoing.headers()['authorization']).toBeUndefined(); expect(outgoing.headers()['cookie']).toBeUndefined();
  } });
  const outage = async (route: import('@playwright/test').Route) => {
    if (route.request().method() === 'PUT' && route.request().url().includes('partNumber=2')) await route.fulfill({ status: 503, headers: { 'Access-Control-Allow-Origin': 'http://127.0.0.1:43000' }, body: 'Provider outage for test' });
    else await route.continue();
  };
  await page.route('http://localhost:9000/**', outage);
  await page.getByLabel('Replacement file', { exact: true }).setInputFiles({ name: 'Replacement.bin', mimeType: 'application/octet-stream', buffer: body });
  await page.getByRole('button', { name: 'Upload new version', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Version part transfer failed');
  await page.unroute('http://localhost:9000/**', outage); await page.reload();
  await expect(page.getByText(/Resume record:/)).toBeVisible();
  const before = puts; const wrong = Buffer.from(body); wrong[0] = 87;
  await page.getByLabel('Replacement file', { exact: true }).setInputFiles({ name: 'Replacement.bin', mimeType: 'application/octet-stream', buffer: wrong });
  await page.getByRole('button', { name: 'Upload new version', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('original file content'); expect(puts).toBe(before);
  await page.getByLabel('Replacement file', { exact: true }).setInputFiles({ name: 'Replacement.bin', mimeType: 'application/octet-stream', buffer: body });
  await page.getByRole('button', { name: 'Upload new version', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Version uploaded and verified'); expect(puts).toBe(before + 1);
  await expect(page.getByText('Current: version 2', { exact: true })).toBeVisible();
  const downloadEvent = page.waitForEvent('download'); await page.getByRole('button', { name: 'Download version 2', exact: true }).click();
  expect(await readFile((await (await downloadEvent).path())!)).toEqual(body);
  await expect(page.getByRole('button', { name: 'Delete version 2', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Delete version 1', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Confirm history deletion' })).toBeDisabled();
  await page.getByLabel('Type DELETE to remove history').fill('DELETE'); await page.getByRole('button', { name: 'Confirm history deletion' }).click();
  await expect(page.getByRole('status')).toContainText('deletion queued');
  await expect(page.getByRole('button', { name: 'Download version 1', exact: true })).toHaveCount(0);
  await page.route('http://localhost:9000/**', outage);
  await page.getByLabel('Replacement file', { exact: true }).setInputFiles({ name: 'Cancelled.bin', mimeType: 'application/octet-stream', buffer: body });
  await page.getByRole('button', { name: 'Upload new version', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Version part transfer failed');
  await page.unroute('http://localhost:9000/**', outage);
  await page.getByRole('button', { name: 'Cancel active upload', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Cancellation recorded');
  await expect(page.getByText('Current: version 2', { exact: true })).toBeVisible();
  await page.getByLabel('Keep newest versions', { exact: true }).fill('1'); await page.getByLabel('Type PRUNE to apply retention').fill('PRUNE');
  await page.getByRole('button', { name: 'Apply retention policy' }).click();
  await expect(page.getByRole('status')).toContainText('Retention policy saved'); await page.reload();
  await expect(page.getByText(/Current policy: keep newest 1/)).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 }); expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});
