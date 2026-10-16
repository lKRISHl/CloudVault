import { readFileSync, writeFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';

test('real scan verdicts appear in the browser and quarantined download/preview fail closed', async ({ page }) => {
  const fixture = JSON.parse(readFileSync('../.local/phase17-browser/fixture.json', 'utf8')) as {
    email: string; password: string; clean: string; blocked: string;
  };
  if (!/^cv_phase17_live_[0-9a-f]{12}@example.com$/.test(fixture.email)) throw Error('Unowned scan fixture');
  try {
    await page.goto('/login');
    await page.getByLabel('Email', { exact: true }).fill(fixture.email);
    await page.getByLabel('Password', { exact: true }).fill(fixture.password);
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await expect(page).toHaveURL(/\/app$/);
    await page.goto('/app/folders');
    const clean = page.getByRole('listitem').filter({ hasText: 'clean.txt' });
    const blocked = page.getByRole('listitem').filter({ hasText: 'detection-test.txt' });
    await expect(clean).toContainText('no known threats detected');
    await expect(blocked).toContainText('Quarantined: a threat or scanner policy violation');
    const denied = page.waitForResponse(response => response.url().includes(`/${fixture.blocked}/download-url`));
    await blocked.getByRole('button', { name: 'Download detection-test.txt', exact: true }).click();
    expect((await denied).status()).toBe(423);
    await expect(blocked.getByRole('alert')).toContainText('Content quarantined');
    await blocked.getByRole('link', { name: 'Preview detection-test.txt', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('Content quarantined');
    await expect(page.locator('main iframe, main object, main embed')).toHaveCount(0);
  } finally {
    writeFileSync('../.local/phase17-browser/done', 'finished');
  }
});
