import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

const password = 'correct-horse-battery';
const suffix = Date.now();

async function link(request: APIRequestContext, email: string, purpose: string) {
  let result = '';
  await expect.poll(async () => {
    const messages = await (await request.get('http://127.0.0.1:48025/messages')).json() as { to: string; body: string }[];
    result = messages.filter((mail) => mail.to === email && mail.body.includes(purpose)).at(-1)?.body.split('\n').find((line) => line.startsWith('http'))?.trim() ?? '';
    return result;
  }).not.toBe('');
  return result;
}

async function register(page: Page, request: APIRequestContext, email: string, workspace: string) {
  await page.goto('/register');
  await page.getByLabel('Full name').fill('Folder Owner');
  await page.getByLabel('Workspace name').fill(workspace);
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Create workspace', exact: true }).click();
  await expect(page).toHaveURL(/\/app$/);
  await page.goto(await link(request, email, 'purpose=verify'));
  await page.getByRole('button', { name: 'Verify email', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Email verified');
  await page.goto('/app/folders');
}

async function create(page: Page, name: string) {
  await page.getByLabel('Folder name', { exact: true }).fill(name);
  await page.getByRole('button', { name: 'Create folder', exact: true }).click();
  await expect(page.getByRole('button', { name: `Open folder ${name}`, exact: true })).toBeVisible();
}

test('folders support nested browsing, rename, safe destination moves and workspace isolation', async ({ page, request }) => {
  const email = `folders-owner-${suffix}@example.com`;
  await register(page, request, email, 'Folder Team');
  await expect(page.getByText('No file metadata here.', { exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Files' })).toContainText('Files remain unscanned');
  await create(page, 'Projects');
  await create(page, 'Archive');
  await page.getByRole('button', { name: 'Open folder Projects', exact: true }).click();
  await expect(page.getByRole('navigation', { name: 'Folder breadcrumbs' })).toContainText('Projects');
  await create(page, 'Designs');
  await page.getByRole('button', { name: 'Rename Designs', exact: true }).click();
  await page.getByLabel('New folder name').fill('Planning');
  await page.getByRole('button', { name: 'Save rename' }).click();
  await expect(page.getByRole('button', { name: 'Open folder Planning', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Move Planning', exact: true }).click();
  await page.getByRole('button', { name: 'Open destination Archive', exact: true }).click();
  await expect(page.getByText('Destination: All folders / Archive', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Move here' }).click();
  await expect(page.getByRole('status')).toContainText('Folder moved');
  await expect(page.getByRole('button', { name: 'Open folder Planning', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'All folders', exact: true }).click();
  await page.getByRole('button', { name: 'Open folder Archive', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Open folder Planning', exact: true })).toBeVisible();
  const previousUrl = page.url();
  await page.goto('/app');
  await page.getByLabel('New workspace name').fill('Empty Folder Team');
  await page.getByRole('button', { name: 'Create another workspace' }).click();
  await expect(page.getByText('Current workspace: Empty Folder Team', { exact: true })).toBeVisible();
  await page.goto(previousUrl);
  await expect(page.getByRole('alert')).toContainText('Folder not found');
  await page.getByRole('button', { name: 'All folders', exact: true }).click();
  await expect(page.getByText('No folders here.', { exact: true })).toBeVisible();
});

test('members see shared folders read-only and can organize folders they create', async ({ page, request, browser }) => {
  const owner = `folders-manager-${suffix}@example.com`;
  const member = `folders-member-${suffix}@example.com`;
  await register(page, request, owner, 'Shared Folder Team');
  await create(page, 'Owner documents');
  await page.goto('/app/settings');
  await page.getByLabel('Invitation email').fill(member);
  await page.getByRole('button', { name: 'Create invitation' }).click();
  await expect(page.getByLabel('Private invitation link')).toBeVisible();
  const context = await browser.newContext();
  const other = await context.newPage();
  await other.goto(await link(request, member, '/join#token='));
  await other.getByLabel('Full name').fill('Folder Member');
  await other.getByLabel('Password', { exact: true }).fill(password);
  await other.getByRole('button', { name: 'Join organization' }).click();
  await expect(other).toHaveURL(/\/app$/);
  await other.goto('/app/folders');
  await expect(other.getByRole('alert')).toContainText('verify your email');
  await other.goto(await link(request, member, 'purpose=verify'));
  await other.getByRole('button', { name: 'Verify email', exact: true }).click();
  await expect(other.getByRole('status')).toContainText('Email verified');
  await other.goto('/app/folders');
  await expect(other.getByRole('button', { name: 'Open folder Owner documents', exact: true })).toBeVisible();
  await expect(other.getByRole('button', { name: 'Rename Owner documents', exact: true })).toHaveCount(0);
  await other.getByRole('button', { name: 'Open folder Owner documents', exact: true }).click();
  await expect(other.getByRole('navigation', { name: 'Folder breadcrumbs' })).toContainText('Owner documents');
  await expect(other.getByRole('button', { name: 'Create folder', exact: true })).toHaveCount(0);
  await other.getByRole('button', { name: 'All folders', exact: true }).click();
  await create(other, 'Member documents');
  await expect(other.getByRole('button', { name: 'Rename Member documents', exact: true })).toBeVisible();
  await context.close();
});
