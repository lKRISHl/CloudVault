import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { TrashPage } from '../features/trash/TrashPage';
import { TrashButton } from '../features/trash/TrashButton';
import { api } from '../services/api';
import type { TrashEntry } from '../types';

vi.mock('../auth/AuthContext', () => ({ useAuth: () => ({ user: { id: 'me', tenant: { id: 'workspace' } } }) }));
const entry: TrashEntry = { id: 'entry', resource_id: 'file', kind: 'files', name: 'Report.pdf', trashed_at: '2026-01-01', retain_until: '2099-01-01', not_before: '2026-01-02', purge_requested_at: null };
function show(content = <TrashPage />) {
  const cache = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return { cache, ...render(<QueryClientProvider client={cache}><MemoryRouter>{content}</MemoryRouter></QueryClientProvider>) };
}
beforeEach(() => {
  vi.spyOn(api, 'trash').mockResolvedValue({ items: [entry], offset: 0, has_more: false });
  vi.spyOn(api, 'restoreTrash').mockResolvedValue(); vi.spyOn(api, 'purgeTrash').mockResolvedValue({ detail: 'Queued' });
});
afterEach(() => vi.restoreAllMocks());

it('lists authorized trash and restores original permissions', async () => {
  const { cache } = show(); await screen.findByText('Report.pdf');
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Restore Report.pdf' })); });
  expect(api.restoreTrash).toHaveBeenCalledWith('entry');
  expect(await screen.findByRole('status')).toHaveTextContent('original permissions');
  expect(cache.getQueryCache().findAll({ queryKey: ['trash', 'workspace', 'me'] })).toHaveLength(1);
});

it('requires DELETE confirmation and reports queued rather than completed purge', async () => {
  show(); await screen.findByText('Report.pdf'); const user = userEvent.setup();
  await act(async () => { await user.click(screen.getByRole('button', { name: 'Delete permanently Report.pdf' })); });
  expect(screen.getByRole('button', { name: 'Confirm permanent deletion' })).toBeDisabled();
  await act(async () => { await user.type(screen.getByLabelText('Type DELETE to permanently delete'), 'DELETE'); await user.click(screen.getByRole('button', { name: 'Confirm permanent deletion' })); });
  expect(api.purgeTrash).toHaveBeenCalledWith('entry', 'DELETE');
  expect(await screen.findByRole('status')).toHaveTextContent('Permanent deletion queued');
});

it('disables restore for queued or expired entries', async () => {
  vi.mocked(api.trash).mockResolvedValue({ items: [{ ...entry, purge_requested_at: '2026-01-03' }, { ...entry, id: 'expired', name: 'Expired.pdf', retain_until: '2000-01-01' }], offset: 0, has_more: false });
  show(); await screen.findByText('Report.pdf');
  expect(screen.getByRole('button', { name: 'Restore Report.pdf' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Restore Expired.pdf' })).toBeDisabled();
});

it('shows restore conflicts and supports paginated trash', async () => {
  vi.mocked(api.trash).mockImplementation(async offset => ({ items: [{ ...entry, name: offset ? 'Next.pdf' : 'Report.pdf' }], offset: offset ?? 0, has_more: !offset }));
  vi.mocked(api.restoreTrash).mockRejectedValue(new Error('Original names are occupied'));
  show(); await screen.findByText('Report.pdf');
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Restore Report.pdf' })); });
  expect(await screen.findByRole('alert')).toHaveTextContent('Original names are occupied');
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Next trash' })); });
  expect(await screen.findByText('Next.pdf')).toBeVisible(); expect(api.trash).toHaveBeenLastCalledWith(25, expect.any(AbortSignal));
});

it('moves a managed resource to recoverable trash and reports errors', async () => {
  vi.spyOn(api, 'moveToTrash').mockRejectedValueOnce(new Error('Finish uploads first')).mockResolvedValueOnce(entry);
  show(<TrashButton kind="folders" id="folder" name="Project" />);
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Move Project to trash' })); });
  expect(await screen.findByRole('alert')).toHaveTextContent('Finish uploads first');
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Move Project to trash' })); });
  expect(api.moveToTrash).toHaveBeenCalledWith('folders', 'folder');
});
