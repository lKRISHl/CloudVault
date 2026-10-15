import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { FileRecoveryActions } from '../features/folders/FileRecoveryActions';
import { TrashButton } from '../features/trash/TrashButton';
import { TrashPage } from '../features/trash/TrashPage';
import { api } from '../services/api';
import type { FileMetadata } from '../types';

vi.mock('../auth/AuthContext', () => ({ useAuth: () => ({ user: { id: 'me', tenant: { id: 'workspace' } } }) }));
const file: FileMetadata = { id: 'file', folder_id: 'source', tenant_id: 'workspace', created_by: 'me', name: 'Report.pdf', status: 'uploaded', declared_size_bytes: 12, declared_content_type: null, can_write: true, can_manage: true, created_at: '', updated_at: '' };
function show(content: React.ReactNode) {
  const cache = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={cache}><MemoryRouter>{content}</MemoryRouter></QueryClientProvider>);
}
beforeEach(() => {
  vi.spyOn(api, 'folders').mockResolvedValue({ parent: null, breadcrumbs: [], items: [], offset: 0, limit: 25, has_more: false });
  vi.spyOn(api, 'moveFile').mockResolvedValue(file);
  vi.spyOn(api, 'discardMetadata').mockResolvedValue();
  vi.spyOn(api, 'cancelUploadsAndTrash').mockResolvedValue({ id: 'trash', resource_id: 'folder', kind: 'folders', name: 'Folder', trashed_at: '', retain_until: '', not_before: '', purge_requested_at: null });
  vi.spyOn(api, 'restoreTrash').mockResolvedValue();
  vi.spyOn(api, 'trash').mockResolvedValue({ items: [{ id: 'trash', resource_id: 'file', kind: 'files', name: 'Report.pdf', trashed_at: '2026-01-01', retain_until: '2099-01-01', not_before: '', purge_requested_at: null }], offset: 0, has_more: false });
});
afterEach(() => vi.restoreAllMocks());

it('moves with the original source and handles location conflicts', async () => {
  vi.mocked(api.moveFile).mockRejectedValue(new Error('File location changed; refresh'));
  show(<FileRecoveryActions file={file} />);
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Move Report.pdf' })); });
  await screen.findByRole('button', { name: 'Move here' });
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Move here' })); });
  expect(api.moveFile).toHaveBeenCalledWith('file', null, 'source');
  expect(await screen.findByRole('alert')).toHaveTextContent('File location changed');
});

it('requires explicit legacy discard confirmation', async () => {
  show(<FileRecoveryActions file={{ ...file, status: 'pending', legacy_metadata: true }} />);
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Discard metadata Report.pdf' })); });
  expect(screen.getByRole('button', { name: 'Confirm metadata discard' })).toBeDisabled();
  await act(async () => { await userEvent.type(screen.getByLabelText('Type DISCARD to discard metadata'), 'DISCARD'); await userEvent.click(screen.getByRole('button', { name: 'Confirm metadata discard' })); });
  expect(api.discardMetadata).toHaveBeenCalledWith('file', 'DISCARD');
});

it('requires cancellation confirmation before trashing pending folder uploads', async () => {
  show(<TrashButton kind="folders" id="folder" name="Folder" />);
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Cancel uploads and trash Folder' })); });
  expect(screen.getByRole('button', { name: 'Confirm cancellation and trash' })).toBeDisabled();
  await act(async () => { await userEvent.type(screen.getByLabelText('Type CANCEL UPLOADS to continue'), 'CANCEL UPLOADS'); await userEvent.click(screen.getByRole('button', { name: 'Confirm cancellation and trash' })); });
  expect(api.cancelUploadsAndTrash).toHaveBeenCalledWith('folder', 'CANCEL UPLOADS');
});

it('restores with an explicit destination and changed name', async () => {
  show(<TrashPage />);
  await screen.findByText('Report.pdf');
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Restore elsewhere Report.pdf' })); });
  await screen.findByRole('button', { name: 'Restore here' });
  await act(async () => { await userEvent.clear(screen.getByLabelText('Restored name')); await userEvent.type(screen.getByLabelText('Restored name'), 'Recovered.pdf'); await userEvent.click(screen.getByRole('button', { name: 'Restore here' })); });
  expect(api.restoreTrash).toHaveBeenCalledWith('trash', { use_original: false, destination_id: null, name: 'Recovered.pdf' });
});

it('pages destinations and prevents choosing a read-only folder', async () => {
  const folder = { id: 'target', tenant_id: 'workspace', parent_id: null, created_by: 'other', name: 'Read only', can_write: false, created_at: '', updated_at: '' };
  vi.mocked(api.folders).mockImplementation(async (parent, offset) => ({ parent: parent ? folder : null, breadcrumbs: parent ? [folder] : [], items: parent ? [] : [folder], offset: offset ?? 0, limit: 25, has_more: !parent && !offset }));
  show(<FileRecoveryActions file={file} />);
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Move Report.pdf' })); });
  await screen.findByRole('button', { name: 'Open destination Read only' });
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Next destinations' })); });
  expect(api.folders).toHaveBeenCalledWith(null, 25, expect.any(AbortSignal));
  await screen.findByRole('button', { name: 'Open destination Read only' });
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Open destination Read only' })); });
  await screen.findByText('Destination: All folders / Read only');
  expect(screen.getByRole('button', { name: 'Move here' })).toBeDisabled();
});
