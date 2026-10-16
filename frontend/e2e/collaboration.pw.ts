import { expect, test } from '@playwright/test';

for (const width of [1280, 390]) {
  test(`folder sharing and member search at ${width}px`, async ({ page, request, browser }) => {
    test.setTimeout(90000);
    await page.setViewportSize({ width, height: 844 });
    const email = `collaboration-${width}-${Date.now()}@example.com`;
    await page.goto('/register');
    await page.getByLabel('Full name').fill('Collaboration Owner');
    await page.getByLabel('Workspace name').fill('Collaboration Team');
    await page.getByLabel('Email', { exact: true }).fill(email);
    await page.getByLabel('Password', { exact: true }).fill('correct-horse-battery');
    await page.getByRole('button', { name: 'Create workspace', exact: true }).click();
    await expect(page).toHaveURL(/\/app$/);
    let verification = '';
    await expect.poll(async () => {
      const messages = await (await request.get('http://127.0.0.1:48025/messages')).json() as { to: string; body: string }[];
      verification = messages.filter(mail => mail.to === email && mail.body.includes('purpose=verify')).at(-1)?.body.split('\n').find(line => line.startsWith('http'))?.trim() ?? '';
      return verification;
    }).not.toBe('');
    await page.goto(verification);
    await page.getByRole('button', { name: 'Verify email', exact: true }).click();
    await page.goto('/app/groups');
    await page.getByLabel('New group name').fill('Client reviewers');
    await page.getByRole('button', { name: 'Create group', exact: true }).click();
    await expect(page.getByRole('region', { name: 'Group membership' })).toContainText('Client reviewers');
    await page.goto('/app/folders');
    await page.getByLabel('Folder name', { exact: true }).fill('Shared client documents');
    await page.getByRole('button', { name: 'Create folder', exact: true }).click();
    await page.getByRole('link', { name: 'Permissions for Shared client documents', exact: true }).click();
    await page.getByLabel('Workspace group').selectOption({ label: 'Client reviewers' });
    await page.getByRole('button', { name: 'Save group access', exact: true }).click();
    await expect(page.getByRole('status')).toContainText('Group access saved');
    await page.getByLabel('Search members by name or email').fill(email);
    await expect(page.getByRole('option', { name: `Collaboration Owner · ${email}` })).toBeVisible();
    await page.goto('/app/folders');
    await page.getByRole('link', { name: 'Share Shared client documents', exact: true }).click();
    await page.getByRole('button', { name: 'Create share link', exact: true }).click();
    const shareUrl = await page.getByLabel('New share URL').inputValue();
    const guest = await browser.newContext({ viewport: { width, height: 844 } });
    try {
      const recipient = await guest.newPage();
      await recipient.goto(shareUrl);
      await recipient.getByRole('button', { name: 'Open shared file', exact: true }).click();
      await expect(recipient.getByRole('region', { name: 'Shared folder' })).toContainText('Shared client documents');
      await expect(recipient.getByText('No available items.')).toBeVisible();
      expect(await recipient.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
      await page.getByRole('button', { name: /^Revoke link / }).click();
      await recipient.getByRole('button', { name: 'Open shared file', exact: true }).click();
      await expect(recipient.getByRole('alert')).toContainText('Share unavailable');
    } finally { await guest.close(); }
  });
}
