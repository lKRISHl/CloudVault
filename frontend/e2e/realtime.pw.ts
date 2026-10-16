import { expect, test, type Page, type APIRequestContext } from '@playwright/test';

test.skip(!process.env.TEST_REDIS_URL, 'Realtime acceptance needs separately selected development/test Redis');

async function verifiedOwner(page: Page, request: APIRequestContext, email: string) {
  await page.goto('/register');
  await page.getByLabel('Full name').fill('Live Owner');
  await page.getByLabel('Workspace name').fill('First Live Workspace');
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill('correct-horse-battery');
  await page.getByRole('button', { name: 'Create workspace', exact: true }).click();
  await expect(page).toHaveURL(/\/app$/);
  let link = '';
  await expect.poll(async () => {
    const messages = await (await request.get('http://127.0.0.1:48025/messages')).json() as { to: string; body: string }[];
    link = messages.filter(mail => mail.to === email).at(-1)?.body.split('\n').find(line => line.startsWith('http'))?.trim() ?? '';
    return link;
  }).not.toBe('');
  await page.goto(link); await page.getByRole('button', { name: 'Verify email', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Email verified');
}

test('shared-cookie switching clears another tab and concurrent reloads keep both sessions usable', async ({ page, context, request }) => {
  test.setTimeout(120000);
  await verifiedOwner(page, request, `live-tabs-${Date.now()}@example.com`);
  await page.goto('/app/folders');
  await page.getByLabel('Folder name', { exact: true }).fill('Only in first workspace');
  await page.getByRole('button', { name: 'Create folder', exact: true }).click();
  const other = await context.newPage(); await other.goto('/app/folders');
  await expect(other.getByRole('button', { name: 'Open folder Only in first workspace', exact: true })).toBeVisible();
  await expect(other.getByLabel('Live updates')).toContainText('connected', { timeout: 15000 });
  await page.goto('/app');
  await page.getByLabel('New workspace name').fill('Second Live Workspace');
  await page.getByRole('button', { name: 'Create another workspace', exact: true }).click();
  await expect(other.locator('.workspace-label strong')).toHaveText('Second Live Workspace', { timeout: 15000 });
  await expect(other.getByRole('button', { name: 'Open folder Only in first workspace', exact: true })).toHaveCount(0);
  await Promise.all([page.reload(), other.reload()]);
  await expect(page).toHaveURL(/\/app/); await expect(other).toHaveURL(/\/app/);
  await expect(other.locator('.workspace-label strong')).toHaveText('Second Live Workspace');
});

test('authorized folder changes arrive live and reconnect discovers changes made offline', async ({ page, context, request }) => {
  test.setTimeout(120000);
  const email = `live-offline-${Date.now()}@example.com`;
  await verifiedOwner(page, request, email); await page.goto('/app/folders');
  await expect(page.getByLabel('Live updates')).toContainText('connected', { timeout: 15000 });
  const session = await (await request.post('http://127.0.0.1:48000/api/v1/auth/login',
    { data: { email, password: 'correct-horse-battery' } })).json();
  const headers = { Authorization: `Bearer ${session.access_token}` };
  const created = await request.post('http://127.0.0.1:48000/api/v1/folders', { headers, data: { name: 'Live arrival' } });
  expect(created.status()).toBe(201);
  await expect(page.getByRole('button', { name: 'Open folder Live arrival', exact: true })).toBeVisible({ timeout: 15000 });
  await context.setOffline(true);
  try {
    expect((await request.post('http://127.0.0.1:48000/api/v1/folders', { headers, data: { name: 'Created while disconnected' } })).status()).toBe(201);
  } finally { await context.setOffline(false); }
  await expect(page.getByRole('button', { name: 'Open folder Created while disconnected', exact: true })).toBeVisible({ timeout: 45000 });
});
