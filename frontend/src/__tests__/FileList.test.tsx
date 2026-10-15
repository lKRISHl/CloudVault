import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { FileList } from '../features/folders/FileList';
import { api, downloadBrowserFile, setAccessToken } from '../services/api';

vi.mock('../auth/AuthContext', () => ({ useAuth: () => ({ user: { id: 'creator', tenant: { id: 'workspace' } } }) }));
const file = { id: 'file', tenant_id: 'workspace', folder_id: null, created_by: 'creator', name: 'Report.pdf', declared_size_bytes: 123,
  declared_content_type: 'application/pdf', status: 'pending' as const, created_at: '', updated_at: '', can_write: false };
function show(folderId: string | null = null) {
  const cache = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={cache}><MemoryRouter><FileList folderId={folderId} /></MemoryRouter></QueryClientProvider>);
  return cache;
}
afterEach(() => vi.restoreAllMocks());

describe('File metadata listing', () => {
  it('shows pending declared metadata without offering downloads and scopes the query', async () => {
    const request = vi.spyOn(api, 'files').mockResolvedValue({ items: [file], offset: 0, limit: 25, has_more: false });
    const cache = show('folder');
    expect(await screen.findByText('Report.pdf')).toBeVisible();
    expect(screen.getByText(/Pending upload · Declared size: 123 bytes/)).toBeVisible();
    expect(screen.getByText('Read only')).toBeVisible();
    expect(screen.queryByRole('link', { name: /download/i })).not.toBeInTheDocument();
    expect(request).toHaveBeenCalledWith('folder', 0);
    expect(cache.getQueryData(['files', 'workspace', 'creator', 'folder', 0])).toBeDefined();
  });

  it('loads the next page of metadata and handles an empty page', async () => {
    vi.spyOn(api, 'files').mockImplementation(async (_folder, offset) => ({ items: offset ? [] : [file], offset: offset ?? 0, limit: 25, has_more: !offset }));
    show(); const user = userEvent.setup();
    await screen.findByText('Report.pdf');
    await act(async () => { await user.click(screen.getByRole('button', { name: 'Next files' })); });
    expect(await screen.findByText('No file metadata here.')).toBeVisible();
    expect(api.files).toHaveBeenLastCalledWith(null, 25);
    expect(screen.getByRole('button', { name: 'Previous files' })).toBeEnabled();
  });

  it('shows errors and permits a manual retry', async () => {
    vi.spyOn(api, 'files').mockRejectedValueOnce(new Error('File listing unavailable')).mockResolvedValue({ items: [], offset: 0, limit: 25, has_more: false });
    show(); const user = userEvent.setup();
    expect(await screen.findByRole('alert')).toHaveTextContent('File listing unavailable');
    await act(async () => { await user.click(screen.getByRole('button', { name: 'Retry files' })); });
    expect(await screen.findByText('No file metadata here.')).toBeVisible();
  });
});


describe('Downloads', () => {
  it('streams via a native attachment link without fetching file bytes', async () => {
    const spy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function(this: HTMLAnchorElement) {
      expect(this.referrerPolicy).toBe('no-referrer');
      expect(this.rel).toBe('noopener noreferrer');
      expect(this.href).toBe('https://storage.invalid/download');
    });
    vi.spyOn(api, 'downloadTicket').mockResolvedValue({ file: { ...file, status: 'uploaded' }, download_url: 'https://storage.invalid/download', expires_at: '' });
    await downloadBrowserFile('file');
    expect(spy).toHaveBeenCalledOnce();
    expect(document.querySelector('a[download]')).toBeNull();
  });
  it('rejects a stale workspace response before navigating', async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    vi.spyOn(api, 'downloadTicket').mockImplementation(async () => {
      setAccessToken('different-workspace');
      return { file: { ...file, status: 'uploaded' }, download_url: 'https://storage.invalid/download', expires_at: '' };
    });
    await expect(downloadBrowserFile('file')).rejects.toThrow('Session changed');
    expect(click).not.toHaveBeenCalled();
  });
  it('offers downloads for uploaded read-only files and shows authorization errors', async () => {
    vi.spyOn(api, 'files').mockResolvedValue({ items: [{ ...file, status: 'uploaded' }], offset: 0, limit: 25, has_more: false });
    vi.spyOn(api, 'downloadTicket').mockRejectedValue(new Error('Stored file is unavailable'));
    show(); const user = userEvent.setup();
    const button = await screen.findByRole('button', { name: 'Download Report.pdf' });
    await act(async () => { await user.click(button); });
    expect(await screen.findByRole('alert')).toHaveTextContent('Stored file is unavailable');
    expect(screen.getByRole('button', { name: 'Download Report.pdf' })).toBeEnabled();
  });
});
