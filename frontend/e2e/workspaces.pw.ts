import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

const password = 'correct-horse-battery';
const suffix = Date.now();

async function mail(request: APIRequestContext, email: string, purpose: string) {
  let link = '';
  await expect.poll(async () => {
    const result = await request.get('http://127.0.0.1:48025/messages');
    const messages = await result.json() as { to: string; body: string }[];
    link = messages.filter((item) => item.to === email && item.body.includes(purpose)).at(-1)?.body.split('\n').find((line) => line.startsWith('http'))?.trim() ?? '';
    return link;
  }).not.toBe('');
  return link;
}

async function register(page: Page, request: APIRequestContext, email: string, name: string, workspace: string) {
  await page.goto('/register');
  await page.getByLabel('Full name').fill(name);
  await page.getByLabel('Workspace name').fill(workspace);
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Create workspace', exact: true }).click();
  await expect(page.getByText(name, { exact: true })).toBeVisible();
  await page.goto(await mail(request, email, 'purpose=verify'));
  await page.getByRole('button', { name: 'Verify email', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Email verified');
}

async function invite(page: Page, request: APIRequestContext, email: string, role = 'member') {
  await page.goto('/app/settings');
  await page.getByLabel('Invitation email').fill(email);
  await page.getByLabel('Invitation role').selectOption(role);
  const preview = page.getByLabel('Private invitation link');
  const previous = await preview.count() ? await preview.inputValue() : '';
  await page.getByRole('button', { name: 'Create invitation' }).click();
  await expect(preview).toBeVisible();
  await expect(preview).not.toHaveValue(previous);
  const expected = await preview.inputValue();
  await expect.poll(() => mail(request, email, '/join#token=')).toBe(expected);
  return expected;
}

async function accept(page: Page, link: string) {
  await page.goto(link);
  await page.getByRole('button', { name: 'Join organization' }).click();
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByRole('heading', { name: 'Your workspaces' })).toBeVisible();
  await expect(page.getByText('Loading workspaces…', { exact: true })).toHaveCount(0);
}

async function transfer(page: Page, email: string) {
  await page.goto('/app/settings');
  await page.getByLabel('New owner', { exact: true }).selectOption({ label: email });
  await page.getByLabel('Ownership transfer password').fill(password);
  await page.getByLabel('Type TRANSFER to confirm').fill('TRANSFER');
  await page.getByRole('button', { name: 'Transfer ownership', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Ownership transferred');
}

test('existing identity joins, switches with scoped permissions, and is removed/reactivated in one workspace', async ({ page, request, browser }) => {
  test.setTimeout(90000);
  const owner = `workspace-owner-${suffix}@example.com`;
  const member = `workspace-member-${suffix}@example.com`;
  await register(page, request, owner, 'Workspace Owner', 'Primary Team');
  const context = await browser.newContext();
  const other = await context.newPage();
  await register(other, request, member, 'Existing Member', 'Personal Team');
  const oldLink = await invite(page, request, member);
  await accept(other, oldLink);
  await other.getByRole('link', { name: 'Profile and organization' }).click();
  await expect(other.getByText('Workspace Owner', { exact: true })).toBeVisible();
  await expect(other.getByRole('button', { name: 'Save organization' })).toHaveCount(0);
  await other.goto('/app');
  await other.getByRole('button', { name: 'Switch to Personal Team' }).click();
  await expect(other.getByText('Current workspace: Personal Team', { exact: true })).toBeVisible();
  await other.goto('/app/settings');
  await expect(other.getByRole('button', { name: 'Save organization' })).toBeVisible();
  await expect(other.getByText('Workspace Owner', { exact: true })).toHaveCount(0);
  const revokedContext = await browser.newContext();
  const revoked = await revokedContext.newPage();
  await revoked.goto('/login');
  await revoked.getByLabel('Email', { exact: true }).fill(member);
  await revoked.getByLabel('Password', { exact: true }).fill(password);
  await revoked.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(revoked.getByText(/^Current workspace:/)).toBeVisible();
  if (await revoked.getByText('Current workspace: Personal Team', { exact: true }).isVisible()) {
    await revoked.getByRole('button', { name: 'Switch to Primary Team' }).click();
  }
  await expect(revoked.getByText('Current workspace: Primary Team', { exact: true })).toBeVisible();
  await page.goto('/app/settings');
  page.on('dialog', (dialog) => dialog.accept());
  const removed = page.waitForResponse((response) => response.request().method() === 'DELETE'
    && response.url().includes('/organizations/current/members/') && response.status() === 204);
  await page.getByRole('button', { name: `Remove ${member}` }).click();
  await removed;
  await expect(page.getByText('Existing Member', { exact: true })).toHaveCount(0);
  await revoked.goto('/app/settings');
  await expect(revoked.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
  await other.goto('/app');
  await expect(other.getByText('Existing Member', { exact: true })).toBeVisible();
  await expect(other.getByRole('button', { name: 'Switch to Primary Team' })).toHaveCount(0);
  await other.goto(oldLink);
  await other.getByRole('button', { name: 'Join organization' }).click();
  await expect(other.getByRole('alert')).toContainText('new reactivation invitation');
  const restoredLink = await invite(page, request, member, 'admin');
  await accept(other, restoredLink);
  await other.getByRole('link', { name: 'Profile and organization' }).click();
  await expect(other.getByRole('button', { name: 'Save organization' })).toBeVisible();
  await expect(other.getByRole('heading', { name: 'Transfer ownership' })).toHaveCount(0);
  await revoked.goto('/app/settings');
  await expect(revoked.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
  await revokedContext.close();
  await context.close();
});

test('workspace creation, ownership transfer and deletion across memberships work in the browser', async ({ page, request, browser }) => {
  test.setTimeout(90000);
  const owner = `transfer-owner-${suffix}@example.com`;
  const member = `transfer-member-${suffix}@example.com`;
  await register(page, request, owner, 'Transfer Owner', 'Original Team');
  const link = await invite(page, request, member);
  const context = await browser.newContext();
  const other = await context.newPage();
  await other.goto(link);
  await other.getByLabel('Full name').fill('Transfer Member');
  await other.getByLabel('Password', { exact: true }).fill(password);
  await other.getByRole('button', { name: 'Join organization' }).click();
  await expect(other).toHaveURL(/\/app$/);
  await other.goto(await mail(request, member, 'purpose=verify'));
  await other.getByRole('button', { name: 'Verify email', exact: true }).click();
  await expect(other.getByRole('status')).toContainText('Email verified');
  await other.goto('/app');
  await other.getByLabel('New workspace name').fill('Additional Team');
  await other.getByRole('button', { name: 'Create another workspace' }).click();
  await expect(other.getByText('Current workspace: Additional Team', { exact: true })).toBeVisible();
  const secondInvite = await invite(other, request, owner);
  await accept(page, secondInvite);
  await transfer(other, owner);
  await other.goto('/app/security');
  await other.getByLabel('Current password', { exact: true }).fill(password);
  await other.getByLabel('Type DELETE to confirm').fill('DELETE');
  await other.getByRole('button', { name: 'Delete my account' }).click();
  await expect(other.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
  await page.goto('/app');
  await page.getByRole('button', { name: 'Switch to Original Team' }).click();
  await expect(page.getByText('Current workspace: Original Team', { exact: true })).toBeVisible();
  await page.goto('/app/settings');
  await expect(page.getByRole('button', { name: 'Save organization' })).toBeVisible();
  await expect(page.locator('#workspace-content').getByText('Transfer Owner', { exact: true })).toBeVisible();
  await expect(page.getByText('Transfer Member', { exact: true })).toHaveCount(0);
  await page.goto('/app');
  await page.getByRole('button', { name: 'Switch to Additional Team' }).click();
  await expect(page.getByText('Current workspace: Additional Team', { exact: true })).toBeVisible();
  await page.goto('/app/settings');
  await expect(page.locator('#workspace-content').getByText('Transfer Owner', { exact: true })).toBeVisible();
  await expect(page.getByText('Transfer Member', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Transfer ownership' })).toBeVisible();
  await context.close();
});
