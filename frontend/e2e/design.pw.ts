import { expect, test } from '@playwright/test';

test('workspace navigation and account actions remain usable on desktop and mobile', async ({ page, request }) => {
  await page.goto('/login');
  await expect(page.getByRole('heading', { name: 'Sign in', exact: true })).toBeVisible();
  await page.screenshot({ path: '../.local/design/login-desktop.png', fullPage: true });
  await page.goto('/register');
  await page.getByLabel('Full name').fill('Design Reviewer');
  await page.getByLabel('Workspace name').fill('Design studio');
  const email = `design-${Date.now()}@example.com`;
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill('correct-horse-battery');
  await page.getByRole('button', { name: 'Create workspace', exact: true }).click();
  await expect(page).toHaveURL(/\/app$/);
  let verification = '';
  await expect.poll(async () => {
    const messages = await (await request.get('http://127.0.0.1:48025/messages')).json() as { to: string; body: string }[];
    verification = messages.filter((mail) => mail.to === email && mail.body.includes('purpose=verify')).at(-1)?.body.split('\n').find((line) => line.startsWith('http'))?.trim() ?? '';
    return verification;
  }).not.toBe('');
  await page.goto(verification);
  await page.getByRole('button', { name: 'Verify email', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Email verified');
  await page.goto('/app');
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Files & folders' }).click();
  await expect(page.getByRole('heading', { name: 'Folders', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Files & folders' })).toHaveAttribute('aria-current', 'page');
  for (const name of ['Brand assets', 'Product design', 'Team documents']) {
    await page.getByLabel('Folder name', { exact: true }).fill(name);
    await page.getByRole('button', { name: 'Create folder', exact: true }).click();
    await expect(page.getByRole('button', { name: `Open folder ${name}`, exact: true })).toBeVisible();
  }
  await page.screenshot({ path: '../.local/design/folders-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('button', { name: 'Sign out', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: '../.local/design/folders-mobile.png', fullPage: true });
  await page.getByRole('link', { name: 'Account security', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Account security and email', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: '../.local/design/login-mobile.png', fullPage: true });
});
