import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import { ShareManagementPage, PublicSharePage } from '../features/sharing/SharingPages';
import { api, publicShareRequest, setAccessToken } from '../services/api';
import type { ShareLink } from '../types';

vi.mock('../auth/AuthContext', () => ({ useAuth: () => ({ user: { id: 'me', tenant: { id: 'workspace' } } }) }));
const link: ShareLink = { id: 'link', file_id: 'file', created_by: 'me', expires_at: '2030-01-01T00:00:00Z', revoked_at: null,
  password_required: true, allow_download: true, max_downloads: 1, download_grants: 0, created_at: '' };
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); setAccessToken(null); window.history.replaceState({}, '', '/'); });

function manage() {
  const cache = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return { cache, ...render(<QueryClientProvider client={cache}><MemoryRouter initialEntries={['/app/files/file/shares']}><Routes><Route path="/app/files/:fileId/shares" element={<ShareManagementPage />} /></Routes></MemoryRouter></QueryClientProvider>) };
}

it('creates protected restricted links, shows a one-time URL and revokes', async () => {
  vi.spyOn(api, 'shares').mockResolvedValue({ file_name: 'Report.txt', items: [link], offset: 0, has_more: false });
  vi.spyOn(api, 'createShare').mockResolvedValue({ ...link, share_url: 'http://localhost/share#token=secret' });
  vi.spyOn(api, 'revokeShare').mockResolvedValue();
  const { cache } = manage(); const user = userEvent.setup();
  await screen.findByText('Password protected', { exact: false });
  await act(async () => {
    await user.type(screen.getByLabelText('Optional link password'), 'separate-password');
    await user.type(screen.getByLabelText('Maximum download grants (optional)'), '1');
    await user.click(screen.getByRole('button', { name: 'Create share link' }));
  });
  expect(api.createShare).toHaveBeenCalledWith('file', expect.objectContaining({ expires_in_hours: 24, password: 'separate-password', allow_download: true, max_downloads: 1, request_id: expect.any(String), token: expect.stringMatching(/^[A-Za-z0-9_-]{43}$/) }), 'files');
  expect(await screen.findByLabelText('New share URL')).toHaveValue('http://localhost/share#token=secret');
  expect(screen.getByLabelText('Optional link password')).toHaveValue('');
  expect(cache.getQueryCache().findAll({ queryKey: ['shares', 'workspace', 'me', 'files', 'file'] })).toHaveLength(1);
  await act(async () => { await user.click(screen.getByRole('button', { name: 'Revoke link link' })); });
  expect(api.revokeShare).toHaveBeenCalledWith('file', 'link', 'files');
  expect(screen.queryByLabelText('New share URL')).not.toBeInTheDocument();
});

it('shows management denial and does not expose creation controls', async () => {
  vi.spyOn(api, 'shares').mockRejectedValue(new Error('Only creator or managers'));
  manage(); expect(await screen.findByRole('alert')).toHaveTextContent('Only creator or managers');
  expect(screen.queryByRole('button', { name: 'Create share link' })).not.toBeInTheDocument();
});

it('opens metadata-only shared files using credentials omitted and clears fragment', async () => {
  window.history.replaceState({}, '', '/share#token=' + 'a'.repeat(43));
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ name: 'Report.txt', size_bytes: 42, expires_at: link.expires_at, allow_download: false, grants_remaining: null }), { status: 200 }));
  vi.stubGlobal('fetch', fetch); setAccessToken('private-account-token');
  render(<MemoryRouter><PublicSharePage /></MemoryRouter>);
  expect(window.location.hash).toBe('');
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Open shared file' })); });
  expect(await screen.findByText('Report.txt')).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Download shared file' })).not.toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/shares/access'), expect.objectContaining({ credentials: 'omit', referrerPolicy: 'no-referrer', cache: 'no-store', headers: { 'Content-Type': 'application/json', Accept: 'application/json' } }));
});

it('handles wrong passwords and streams a checked grant using native navigation', async () => {
  window.history.replaceState({}, '', '/share#token=' + 'a'.repeat(43));
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Share unavailable' }), { status: 404 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ name: 'Report.txt', size_bytes: 42, expires_at: link.expires_at, allow_download: true, grants_remaining: 1 }), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ name: 'Report.txt', download_url: 'https://storage.invalid/file' }), { status: 200 }));
  vi.stubGlobal('fetch', fetch); const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  render(<MemoryRouter><PublicSharePage /></MemoryRouter>); const user = userEvent.setup();
  await act(async () => { await user.click(screen.getByRole('button', { name: 'Open shared file' })); });
  expect(await screen.findByRole('alert')).toHaveTextContent('Share unavailable');
  await act(async () => { await user.type(screen.getByLabelText('Link password'), 'correct-password'); await user.click(screen.getByRole('button', { name: 'Open shared file' })); });
  await screen.findByText('Report.txt');
  await act(async () => { await user.click(screen.getByRole('button', { name: 'Download shared file' })); });
  expect(click).toHaveBeenCalledOnce();
  expect(click.mock.instances[0]).toHaveProperty('referrerPolicy', 'no-referrer');
  expect(screen.queryByRole('button', { name: 'Download shared file' })).not.toBeInTheDocument();
  expect(fetch.mock.calls[2][1].body).toContain('correct-password');
});

it('cancels public access on navigation and never refreshes a signed-in session', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'denied' }), { status: 401 }));
  vi.stubGlobal('fetch', fetch); setAccessToken('private');
  await expect(publicShareRequest('access', { token: 'a'.repeat(43), password: '' })).rejects.toThrow('denied');
  expect(fetch).toHaveBeenCalledOnce();
  window.history.replaceState({}, '', '/share#token=' + 'a'.repeat(43));
  fetch.mockImplementation(() => new Promise(() => {}));
  const view = render(<MemoryRouter><PublicSharePage /></MemoryRouter>);
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Open shared file' })); });
  const signal = fetch.mock.calls[1][1].signal as AbortSignal;
  view.unmount(); expect(signal.aborted).toBe(true);
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
});

it('adopts another share link in the same tab and clears previous credentials and metadata', async () => {
  window.history.replaceState({}, '', '/share#token=' + 'a'.repeat(43));
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ name: 'First.txt', size_bytes: 42, expires_at: link.expires_at, allow_download: false, grants_remaining: null }), { status: 200 }));
  vi.stubGlobal('fetch', fetch); render(<MemoryRouter><PublicSharePage /></MemoryRouter>);
  const user = userEvent.setup();
  await act(async () => { await user.type(screen.getByLabelText('Link password'), 'old-password'); await user.click(screen.getByRole('button', { name: 'Open shared file' })); });
  expect(await screen.findByText('First.txt')).toBeVisible();
  await act(async () => { window.history.replaceState({}, '', '/share#token=' + 'b'.repeat(43)); window.dispatchEvent(new HashChangeEvent('hashchange')); });
  expect(screen.getByLabelText('Link password')).toHaveValue('');
  expect(screen.queryByText('First.txt')).not.toBeInTheDocument();
  expect(window.location.hash).toBe('');
  fetch.mockResolvedValue(new Response(JSON.stringify({ name: 'Second.txt', size_bytes: 42, expires_at: link.expires_at, allow_download: false, grants_remaining: null }), { status: 200 }));
  await act(async () => { await user.click(screen.getByRole('button', { name: 'Open shared file' })); });
  expect(await screen.findByText('Second.txt')).toBeVisible();
  expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ token: 'b'.repeat(43), password: '' });
});


it('retries ambiguous creation with the same request and secret, then changes them for new options', async () => {
  vi.spyOn(api, 'shares').mockResolvedValue({ file_name: 'Report.txt', items: [], offset: 0, has_more: false });
  const create = vi.spyOn(api, 'createShare').mockRejectedValue(new Error('Reply lost'));
  manage(); const user = userEvent.setup();
  await screen.findByRole('button', { name: 'Create share link' });
  await user.click(screen.getByRole('button', { name: 'Create share link' }));
  await screen.findByRole('alert');
  const original = create.mock.calls[0][1];
  await user.click(screen.getByRole('button', { name: 'Create share link' }));
  await waitFor(() => expect(create).toHaveBeenCalledTimes(2));
  expect(create.mock.calls[1][1]).toEqual(original);
  await user.type(screen.getByLabelText('Named recipient email (optional)'), 'recipient@example.com');
  await user.click(screen.getByRole('button', { name: 'Create share link' }));
  await waitFor(() => expect(create).toHaveBeenCalledTimes(3));
  expect(create.mock.calls[2][1].request_id).not.toEqual(original.request_id);
});

it('requires explicit recipient proof and browses a shared folder without edit controls', async () => {
  window.history.replaceState({}, '', '/share#token=' + 'a'.repeat(43));
  setAccessToken('verified-account-token');
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ name: 'Client folder', folder_id: 'root', items: [{ id: 'nested', kind: 'folder', name: 'Nested' }], offset: 0, has_more: false, expires_at: link.expires_at }), { status: 200 }));
  vi.stubGlobal('fetch', fetch);
  render(<MemoryRouter><PublicSharePage /></MemoryRouter>);
  await userEvent.click(screen.getByRole('checkbox', { name: /Prove recipient identity/ }));
  await userEvent.click(screen.getByRole('button', { name: 'Open shared file' }));
  expect(await screen.findByRole('region', { name: 'Shared folder' })).toBeVisible();
  expect(fetch).toHaveBeenLastCalledWith(expect.any(String), expect.objectContaining({ credentials: 'omit', headers: expect.objectContaining({ Authorization: 'Bearer verified-account-token' }) }));
  expect(screen.getByRole('button', { name: 'Open folder Nested' })).toBeVisible();
  expect(screen.queryByRole('button', { name: /Upload|Edit/ })).not.toBeInTheDocument();
});
