import { execFileSync } from 'node:child_process';
import { expect, test } from '@playwright/test';

test.skip(!process.env.TEST_S3_ENDPOINT || process.env.TEST_PREVIEW_FIXTURE_RENDERER !== '1',
  'Preview journey needs disposable storage and the owned-fixture renderer');

test('real verified text, image, PDF and historical preview stay inert and work on mobile', async ({ page, request }) => {
  test.setTimeout(90000);
  const email = `preview-${Date.now()}@example.com`;
  await page.goto('/register');
  await page.getByLabel('Full name').fill('Preview Owner');
  await page.getByLabel('Workspace name').fill('Preview Team');
  await page.getByLabel('Email', { exact: true }).fill(email);
  await page.getByLabel('Password', { exact: true }).fill('correct-horse-battery');
  await page.getByRole('button', { name: 'Create workspace', exact: true }).click();
  await expect(page).toHaveURL(/\/app$/);
  let link = '';
  await expect.poll(async () => {
    const messages = await (await request.get('http://127.0.0.1:48025/messages')).json() as { to: string; body: string }[];
    link = messages.filter(item => item.to === email && item.body.includes('purpose=verify')).at(-1)?.body.split('\n').find(line => line.startsWith('http'))?.trim() ?? '';
    return link;
  }, { timeout: 15000 }).not.toBe('');
  await page.goto(link); await page.getByRole('button', { name: 'Verify email', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Email verified');

  async function upload(name: string, buffer: Buffer) {
    await page.goto('/app/folders');
    // A misleading declaration must not select an active renderer.
    await page.getByLabel('File to upload').setInputFiles({ name, mimeType: 'application/octet-stream', buffer });
    await page.getByRole('button', { name: 'Upload file', exact: true }).click();
    await expect(page.getByRole('status').filter({ hasText: 'File uploaded and verified' })).toBeVisible();
    await page.getByRole('link', { name: `Preview ${name}`, exact: true }).click();
  }
  await upload('Misleading.html', Buffer.from('<script>window.previewExecuted=true</script><svg onload="alert(1)"/>'));
  await expect(page.getByLabel('Text preview')).toContainText('<script>');
  expect(await page.evaluate(() => (window as unknown as { previewExecuted?: boolean }).previewExecuted)).toBeUndefined();
  await expect(page.locator('main iframe, main embed, main object, main script, main svg')).toHaveCount(0);
  const previewUrl = page.url();
  await page.getByRole('link', { name: 'Versions and downloads', exact: true }).click();
  await page.getByRole('link', { name: 'Preview version 1', exact: true }).click();
  await expect(page).toHaveURL(/version=/); await expect(page.getByLabel('Text preview')).toContainText('<script>');
  await page.goto(previewUrl); await expect(page.getByLabel('Text preview')).toBeVisible();

  // Generate our own tiny valid fixtures; no external/untrusted native fixture parsing on the host.
  const fixture = (format: string) => execFileSync('python', ['-c',
    `import io,sys; from PIL import Image; b=io.BytesIO(); a=Image.new('RGB',(80,40),'blue'); a.save(b,format='${format}',**({'save_all':True,'append_images':[a.copy()]} if '${format}'=='PDF' else {})); sys.stdout.buffer.write(b.getvalue())`]);
  await upload('Photo.png', fixture('PNG'));
  await expect(page.getByRole('img')).toBeVisible();
  await expect(page.getByRole('img')).toHaveAttribute('src', /^blob:/);
  await upload('Two pages.pdf', fixture('PDF'));
  await expect(page.getByText('Page 1 of 2', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Next PDF page', exact: true }).click();
  await expect(page.getByText('Page 2 of 2', { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await upload('Unsupported.bin', Buffer.from([0, 255, 1]));
  await expect(page.getByRole('status')).toContainText('Unsupported or binary content');
  await expect(page.locator('main iframe, main object, main video, main embed')).toHaveCount(0);
});
