import { expect, test, type Page, type APIRequestContext } from '@playwright/test';

const password = 'correct-horse-battery';
const suffix = Date.now();

async function inboxLink(request: APIRequestContext, email: string, purpose: string): Promise<string> {
  let link = '';
  await expect.poll(async () => {
    const response = await request.get('http://127.0.0.1:48025/messages');
    const messages = await response.json() as { to: string; body: string }[];
    const mail = messages.filter((item) => item.to === email && item.body.includes(purpose)).at(-1);
    link = mail?.body.split('\n').find((line) => line.startsWith('http'))?.trim() ?? '';
    return link;
  }, { timeout: 15000 }).not.toBe('');
  return link;
}

async function register(page: Page, email: string) {
  await page.goto('/register');
  await page.getByLabel('Full name').fill('Browser Owner');
  await page.getByLabel('Workspace name').fill('Browser Workspace');
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Create workspace' }).click();
  await expect(page.getByText('Browser Owner', { exact: true })).toBeVisible();
}

async function signIn(page: Page, email: string, secret = password) {
  await page.goto('/login');
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill(secret);
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByText('Browser Owner', { exact: true })).toBeVisible();
}

test('real SMTP verification unlocks organization features and link replay fails', async ({ page, request }) => {
  const email = `verify-${suffix}@example.com`;
  await register(page, email);
  await page.goto('/app/settings');
  await expect(page.getByRole('alert')).toContainText('Verify your email');
  const link = await inboxLink(request, email, 'purpose=verify');
  await page.goto(link);
  await page.getByRole('button', { name: 'Verify email', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Email verified');
  expect(page.url()).not.toContain('#');
  await page.goto('/app/settings');
  await expect(page.getByRole('button', { name: 'Save organization' })).toBeVisible();
  await page.goto(link);
  await page.getByRole('button', { name: 'Verify email', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Invalid or expired');
});

test('password recovery through real email invalidates old sessions and permits new password', async ({ page, request }) => {
  const email = `reset-${suffix}@example.com`;
  await register(page, email);
  await page.goto('/account/recover');
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByRole('button', { name: 'Request email' }).click();
  await expect(page.getByRole('status')).toContainText('If an eligible account');
  await page.goto(await inboxLink(request, email, 'purpose=reset'));
  await page.getByLabel('New password', { exact: true }).fill('new-browser-password');
  await page.getByLabel('Confirm new password').fill('new-browser-password');
  await page.getByRole('button', { name: 'Reset password', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Password reset');
  await signIn(page, email, 'new-browser-password');
});

test('verified email change requires current password and signs out after confirmation', async ({ page, request }) => {
  const email = `change-${suffix}@example.com`;
  const updated = `changed-${suffix}@example.com`;
  await register(page, email);
  await page.goto(await inboxLink(request, email, 'purpose=verify'));
  await page.getByRole('button', { name: 'Verify email', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Email verified');
  await page.goto('/app/security');
  await page.getByLabel('Current password', { exact: true }).fill(password);
  await page.getByLabel('New email').fill(updated);
  await page.getByRole('button', { name: 'Request email change' }).click();
  await expect(page.getByRole('status')).toContainText('current email is unchanged');
  await page.goto(await inboxLink(request, updated, 'purpose=email_change'));
  await page.getByLabel('Current password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Confirm email change', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Email changed');
  await signIn(page, updated);
});

test('session revocation rejects another browser session and sign out all rejects current session', async ({ page, browser }) => {
  const email = `sessions-${suffix}@example.com`;
  await register(page, email);
  const otherContext = await browser.newContext();
  const other = await otherContext.newPage();
  await signIn(other, email);
  await page.goto('/app/security');
  const row = page.getByRole('listitem').filter({ hasText: 'Other session' });
  await expect(row).toBeVisible();
  await row.getByRole('button', { name: /Revoke session/ }).click();
  await other.goto('/app/security');
  await expect(other.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
  await page.getByLabel('Current password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign out all devices' }).click();
  await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
  await otherContext.close();
});

test('emailed invitations require mailbox verification, members can delete, and owners stay protected', async ({ page, request, browser }) => {
  const ownerEmail = `invite-owner-${suffix}@example.com`;
  const memberEmail = `invite-member-${suffix}@example.com`;
  await register(page, ownerEmail);
  await page.goto(await inboxLink(request, ownerEmail, 'purpose=verify'));
  await page.getByRole('button', { name: 'Verify email', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Email verified');
  await page.goto('/app/security');
  await page.getByLabel('Current password', { exact: true }).fill(password);
  await page.getByLabel('Type DELETE to confirm').fill('DELETE');
  await page.getByRole('button', { name: 'Delete my account' }).click();
  await expect(page.getByRole('alert')).toContainText('Transfer organization ownership');
  await page.goto('/app/settings');
  await page.getByLabel('Invitation email').fill(memberEmail);
  await page.getByRole('button', { name: 'Create invitation' }).click();
  await expect(page.getByLabel('Private invitation link')).toBeVisible();
  const context = await browser.newContext();
  const member = await context.newPage();
  await member.goto(await inboxLink(request, memberEmail, '/join#token='));
  await member.getByLabel('Full name').fill('Browser Member');
  await member.getByLabel('Password', { exact: true }).fill(password);
  await member.getByRole('button', { name: 'Join organization' }).click();
  await expect(member.getByText('Browser Member', { exact: true })).toBeVisible();
  await member.goto('/app/settings');
  await expect(member.getByRole('alert')).toContainText('Verify your email');
  await member.goto(await inboxLink(request, memberEmail, 'purpose=verify'));
  await member.getByRole('button', { name: 'Verify email', exact: true }).click();
  await expect(member.getByRole('status')).toContainText('Email verified');
  await member.goto('/app/security');
  await member.getByLabel('Current password', { exact: true }).fill(password);
  await member.getByLabel('Type DELETE to confirm').fill('DELETE');
  await member.getByRole('button', { name: 'Delete my account' }).click();
  await expect(member.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
  await page.goto('/app/settings');
  await expect(page.getByText('Browser Member', { exact: true })).toHaveCount(0);
  await context.close();
});

test('unknown-account recovery stays generic and invalid links show an error', async ({ page }) => {
  await page.goto('/account/recover');
  await page.getByLabel('Email', { exact: true }).fill(`missing-${suffix}@example.com`);
  await page.getByRole('button', { name: 'Request email' }).click();
  await expect(page.getByRole('status')).toContainText('If an eligible account');
  await page.goto(`/account/action#purpose=verify&token=${'x'.repeat(64)}`);
  await page.getByRole('button', { name: 'Verify email', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Invalid or expired');
});

test('verification remains successful when an old browser session was revoked', async ({ page, request, browser }) => {
  const email = `revoked-verify-${suffix}@example.com`;
  await register(page, email);
  await page.goto(await inboxLink(request, email, 'purpose=verify'));
  await expect(page.getByRole('button', { name: 'Verify email', exact: true })).toBeVisible();
  const context = await browser.newContext();
  const other = await context.newPage();
  await signIn(other, email);
  await other.goto('/app/security');
  await other.getByLabel('Current password', { exact: true }).fill(password);
  await other.getByRole('button', { name: 'Sign out all devices' }).click();
  await expect(other.getByRole('button', { name: 'Sign in', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Verify email', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Email verified');
  expect(page.url()).not.toContain('#');
  await context.close();
});
