import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { PermissionsPage } from '../features/permissions/PermissionsPage';
import { RenameFile } from '../features/folders/RenameFile';
import { api } from '../services/api';

vi.mock('../auth/AuthContext', () => ({ useAuth: () => ({ user: { id: 'me', tenant: { id: 'workspace' } } }) }));
beforeEach(() => {
  vi.spyOn(api, 'permissions').mockResolvedValue({ name: 'Secret.pdf', visibility: 'workspace', items: [], offset: 0, has_more: false });
  vi.spyOn(api, 'members').mockResolvedValue([{ user_id: 'member', full_name: 'Team Member', email: 'member@example.com', role: 'member', joined_at: '' }]);
  vi.spyOn(api, 'setVisibility').mockResolvedValue(); vi.spyOn(api, 'setGrant').mockResolvedValue();
});
afterEach(() => vi.restoreAllMocks());
function show() {
  const cache = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return { cache, ...render(<QueryClientProvider client={cache}><MemoryRouter initialEntries={['/app/permissions/files/file']}><Routes><Route path="/app/permissions/:kind/:id" element={<PermissionsPage />} /></Routes></MemoryRouter></QueryClientProvider>) };
}

it('sets private visibility and uses resource/user/workspace cache identity', async () => {
  const { cache } = show(); const user = userEvent.setup(); await screen.findByText('Secret.pdf');
  await act(async () => { await user.click(screen.getByRole('button', { name: 'Make private' })); });
  expect(api.setVisibility).toHaveBeenCalledWith('files', 'file', 'private');
  expect(await screen.findByRole('status')).toHaveTextContent('Resource is private');
  expect(cache.getQueryCache().findAll({ queryKey: ['permissions', 'workspace', 'me', 'files', 'file'] })).toHaveLength(1);
});

it('grants only viewer/editor roles to selected paginated members', async () => {
  show(); const user = userEvent.setup(); await screen.findByRole('option', { name: 'Team Member · member@example.com' });
  expect(screen.queryByRole('option', { name: 'Owner' })).not.toBeInTheDocument();
  await act(async () => { await user.selectOptions(screen.getByLabelText('Workspace member'), 'member'); await user.selectOptions(screen.getByLabelText('Resource role'), 'editor'); await user.click(screen.getByRole('button', { name: 'Save member access' })); });
  expect(api.setGrant).toHaveBeenCalledWith('files', 'file', 'member', 'editor');
  expect(await screen.findByRole('status')).toHaveTextContent('Member access saved');
});

it('removes grants while explaining workspace access still applies', async () => {
  vi.mocked(api.permissions).mockResolvedValue({ name: 'Secret.pdf', visibility: 'workspace', items: [{ user_id: 'member', role: 'viewer' }], offset: 0, has_more: false });
  show(); await screen.findByRole('button', { name: 'Remove access member' });
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Remove access member' })); });
  expect(api.setGrant).toHaveBeenCalledWith('files', 'file', 'member', null);
  expect(await screen.findByRole('status')).toHaveTextContent('Workspace visibility');
});

it('does not show permission actions on denial and offers retry', async () => {
  vi.mocked(api.permissions).mockRejectedValue(new Error('Management access required'));
  show(); expect(await screen.findByRole('alert')).toHaveTextContent('Management access required');
  expect(screen.queryByRole('button', { name: 'Make private' })).not.toBeInTheDocument();
  vi.mocked(api.permissions).mockResolvedValue({ name: 'Secret.pdf', visibility: 'private', items: [], offset: 0, has_more: false });
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Retry permissions' })); });
  expect(await screen.findByRole('button', { name: 'Make private' })).toBeDisabled();
});

it('pages member candidates and clears the previous selection', async () => {
  vi.mocked(api.members).mockImplementation(async offset => Array.from({ length: offset ? 1 : 25 }, (_, i) => ({ user_id: `${offset}-${i}`, full_name: `Member ${offset}-${i}`, email: `${offset}-${i}@example.com`, role: 'member', joined_at: '' })));
  show(); const user = userEvent.setup(); await screen.findByRole('option', { name: 'Member 0-0 · 0-0@example.com' });
  await act(async () => { await user.selectOptions(screen.getByLabelText('Workspace member'), '0-0'); await user.click(screen.getByRole('button', { name: 'Next members' })); });
  expect(await screen.findByRole('option', { name: 'Member 25-0 · 25-0@example.com' })).toBeVisible();
  expect(screen.getByLabelText('Workspace member')).toHaveValue('');
  expect(api.members).toHaveBeenLastCalledWith(25, 25);
});

it('renames completed files and reports conflicts without losing the form', async () => {
  vi.spyOn(api, 'renameFile').mockRejectedValueOnce(new Error('File metadata conflict')).mockResolvedValueOnce({} as never);
  const cache = new QueryClient(); render(<QueryClientProvider client={cache}><RenameFile id="file" name="Old.txt" /></QueryClientProvider>);
  const user = userEvent.setup();
  await act(async () => { await user.click(screen.getByRole('button', { name: 'Rename file Old.txt' })); });
  await screen.findByLabelText('New filename');
  await act(async () => { await user.clear(screen.getByLabelText('New filename')); await user.type(screen.getByLabelText('New filename'), 'New.txt'); await user.click(screen.getByRole('button', { name: 'Save filename' })); });
  expect(await screen.findByRole('alert')).toHaveTextContent('File metadata conflict');
  await act(async () => { await user.click(screen.getByRole('button', { name: 'Save filename' })); });
  await waitFor(() => expect(screen.queryByLabelText('New filename')).not.toBeInTheDocument());
  expect(api.renameFile).toHaveBeenCalledWith('file', 'New.txt');
});
