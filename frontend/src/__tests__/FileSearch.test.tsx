import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { FileSearchPage } from '../features/search/FileSearchPage';
import { api, beginSessionChange, setAccessToken } from '../services/api';
import type { FileMetadata } from '../types';

let tenant = 'workspace';
vi.mock('../auth/AuthContext', () => ({ useAuth: () => ({ user: { id: 'me', tenant: { id: tenant } } }) }));
const file: FileMetadata = { id: 'file', tenant_id: 'workspace', created_by: 'other', folder_id: 'folder', name: 'Report.pdf',
  declared_size_bytes: 100, declared_content_type: 'application/pdf', status: 'uploaded', size_bytes: 100,
  created_at: '', updated_at: '', can_write: false };
function show(url = '/app/search') {
  const cache = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const tree = () => <QueryClientProvider client={cache}><MemoryRouter initialEntries={[url]}><FileSearchPage /></MemoryRouter></QueryClientProvider>;
  return { ...render(tree()), cache, tree };
}
beforeEach(() => {
  tenant = 'workspace';
  vi.spyOn(api, 'searchFiles').mockResolvedValue({ items: [file], offset: 0, limit: 25, has_more: false });
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('shows scoped results, folder links and downloads for read-only uploaded files', async () => {
  const { cache } = show();
  expect(await screen.findByText('Report.pdf')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Download Report.pdf' })).toBeEnabled();
  expect(screen.getByRole('link', { name: 'Open folder for Report.pdf' })).toHaveAttribute('href', '/app/folders?folder=folder');
  expect(api.searchFiles).toHaveBeenCalledWith(expect.objectContaining({ scope: 'workspace', offset: 0, limit: 25 }), expect.any(AbortSignal));
  expect(cache.getQueryCache().findAll({ queryKey: ['file-search', 'workspace', 'me'] })).toHaveLength(1);
});

it('submits filename, metadata, size, creator, scope and sort filters', async () => {
  show(); const user = userEvent.setup(); await screen.findByText('Report.pdf');
  await act(async () => {
    await user.type(screen.getByLabelText('Filename'), '50%');
    await user.selectOptions(screen.getByLabelText('Search scope'), 'root');
    await user.selectOptions(screen.getByLabelText('Upload status'), 'uploaded');
    await user.selectOptions(screen.getByLabelText('Transfer method'), 'basic');
    await user.type(screen.getByLabelText('Declared type'), 'text/plain');
    await user.type(screen.getByLabelText('Minimum bytes'), '10');
    await user.type(screen.getByLabelText('Maximum bytes'), '50');
    await user.selectOptions(screen.getByLabelText('Sort by'), 'size');
    await user.selectOptions(screen.getByLabelText('Sort direction'), 'desc');
    await user.click(screen.getByLabelText('Created by me'));
    await user.click(screen.getByRole('button', { name: 'Search files' }));
  });
  await waitFor(() => expect(api.searchFiles).toHaveBeenLastCalledWith(expect.objectContaining({ q: '50%', scope: 'root',
    status: 'uploaded', upload_method: 'basic', declared_content_type: 'text/plain', min_bytes: 10, max_bytes: 50,
    created_by: 'me', sort: 'size', direction: 'desc', offset: 0 }), expect.any(AbortSignal)));
});

it('paginates and resets to the first page when search changes', async () => {
  vi.mocked(api.searchFiles).mockImplementation(async params => ({ items: [{ ...file, name: params.offset ? 'Next.pdf' : 'First.pdf' }], offset: params.offset ?? 0, limit: 25, has_more: !params.offset }));
  show(); const user = userEvent.setup(); await screen.findByText('First.pdf');
  await act(async () => { await user.click(screen.getByRole('button', { name: 'Next results' })); });
  expect(await screen.findByText('Next.pdf')).toBeVisible();
  await act(async () => { await user.type(screen.getByLabelText('Filename'), 'Changed'); await user.click(screen.getByRole('button', { name: 'Search files' })); });
  await waitFor(() => expect(api.searchFiles).toHaveBeenLastCalledWith(expect.objectContaining({ q: 'Changed', offset: 0 }), expect.any(AbortSignal)));
});

it('resets search and hides cached prior-workspace results after workspace change', async () => {
  const view = show(); await screen.findByText('Report.pdf');
  vi.mocked(api.searchFiles).mockResolvedValue({ items: [], offset: 0, limit: 25, has_more: false });
  tenant = 'other'; view.rerender(view.tree());
  await waitFor(() => expect(screen.queryByText('Report.pdf')).not.toBeInTheDocument());
  expect(api.searchFiles).toHaveBeenLastCalledWith(expect.objectContaining({ scope: 'workspace', offset: 0 }), expect.any(AbortSignal));
  expect(view.cache.getQueryCache().findAll({ queryKey: ['file-search', 'other', 'me'] })).toHaveLength(1);
});

it('validates size ranges and exposes manual retry for safe errors', async () => {
  vi.mocked(api.searchFiles).mockRejectedValueOnce(new Error('Search unavailable')).mockResolvedValue({ items: [], offset: 0, limit: 25, has_more: false });
  show(); const user = userEvent.setup();
  expect(await screen.findByRole('alert')).toHaveTextContent('Search unavailable');
  await act(async () => { await user.click(screen.getByRole('button', { name: 'Retry search' })); });
  await waitFor(() => expect(screen.getByRole('button', { name: 'Search files' })).toBeEnabled());
  await act(async () => { await user.type(screen.getByLabelText('Minimum bytes'), '100'); await user.type(screen.getByLabelText('Maximum bytes'), '10'); await user.click(screen.getByRole('button', { name: 'Search files' })); });
  expect(screen.getByRole('alert')).toHaveTextContent('minimum no greater than maximum');
});

it('uses selected-folder scope and clears it with the filters', async () => {
  show('/app/search?folder=chosen'); await screen.findByText('Report.pdf'); const user = userEvent.setup();
  expect(api.searchFiles).toHaveBeenCalledWith(expect.objectContaining({ scope: 'folder', folder_id: 'chosen' }), expect.any(AbortSignal));
  await act(async () => { await user.click(screen.getByRole('button', { name: 'Clear filters' })); });
  await waitFor(() => expect(api.searchFiles).toHaveBeenLastCalledWith(expect.objectContaining({ scope: 'workspace', offset: 0 }), expect.any(AbortSignal)));
});

it('encodes literal filename characters and rejects stale API responses', async () => {
  vi.restoreAllMocks(); setAccessToken('search-test');
  const fetchMock = vi.fn().mockImplementation(async () => { beginSessionChange(); return { ok: true, status: 200, json: async () => ({ items: [] }) }; });
  vi.stubGlobal('fetch', fetchMock);
  await expect(api.searchFiles({ q: '50%_ & résumé', min_bytes: 0 })).rejects.toThrow('changed');
  expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('q=50%25_+%26+r%C3%A9sum%C3%A9&min_bytes=0'), expect.any(Object));
});
