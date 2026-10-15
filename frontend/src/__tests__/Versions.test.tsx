import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { VersionsPage } from '../features/versions/VersionsPage';
import { api } from '../services/api';
import type { VersionPage } from '../types';

vi.mock('../auth/AuthContext', () => ({ useAuth: () => ({ user: { id: 'me', tenant: { id: 'workspace' } } }) }));
const page: VersionPage = { file: { id: 'file', tenant_id: 'workspace', folder_id: null, created_by: 'me', name: 'Report.txt', declared_size_bytes: 10, declared_content_type: 'text/plain', status: 'uploaded', created_at: '2026-01-01', updated_at: '2026-01-01', can_write: true, current_version: 2, version_generation: 4 },
  items: [{ id: 'old', number: 1, created_by: 'me', created_at: '2026-01-01', completed_at: '2026-01-01', status: 'uploaded', size_bytes: 7, declared_size_bytes: 7, checksum_sha256: 'abc', checksum_kind: 'sha256', is_current: false, expires_at: '2026-01-01', can_complete: false }], offset: 0, has_more: false, retained_bytes: 17, pending_bytes: 0 };
function show() {
  const cache = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={cache}><MemoryRouter initialEntries={['/app/files/file/versions']}><Routes><Route path="/app/files/:fileId/versions" element={<VersionsPage />} /></Routes></MemoryRouter></QueryClientProvider>);
  return cache;
}
beforeEach(() => {
  vi.spyOn(api, 'versions').mockResolvedValue(page);
  vi.spyOn(api, 'uploadConfiguration').mockResolvedValue({ enabled: true, max_bytes: 100 });
  vi.spyOn(api, 'restoreVersion').mockResolvedValue(page.file);
});
afterEach(() => { vi.restoreAllMocks(); sessionStorage.clear(); });

it('shows scoped history and restores only after confirmation using the generation', async () => {
  const cache = show(); await screen.findByText('Report.txt');
  expect(screen.getByText('Retained bytes: 17 · Pending declared bytes: 0')).toBeVisible();
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Restore version 1' })); });
  expect(api.restoreVersion).not.toHaveBeenCalled();
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Confirm restore' })); });
  expect(api.restoreVersion).toHaveBeenCalledWith('file', 'old', 4, expect.any(AbortSignal));
  expect(await screen.findByRole('status')).toHaveTextContent('Version restored');
  expect(cache.getQueryCache().findAll({ queryKey: ['versions', 'workspace', 'me', 'file'] })).toHaveLength(1);
});

it('readers can download history while write controls remain absent', async () => {
  vi.mocked(api.versions).mockResolvedValue({ ...page, file: { ...page.file, can_write: false } });
  show(); await screen.findByText('Report.txt');
  expect(screen.getByRole('button', { name: 'Download version 1' })).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Restore version 1' })).not.toBeInTheDocument();
  expect(screen.queryByLabelText('Replacement file')).not.toBeInTheDocument();
});

it('reports stale restoration and paginates history', async () => {
  vi.mocked(api.restoreVersion).mockRejectedValue(new Error('Current version changed'));
  vi.mocked(api.versions).mockImplementation(async (_id, offset = 0) => ({ ...page, offset, has_more: !offset }));
  show(); await screen.findByText('Report.txt');
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Restore version 1' })); });
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Confirm restore' })); });
  expect(await screen.findByRole('alert')).toHaveTextContent('Current version changed');
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Next versions' })); });
  expect(api.versions).toHaveBeenLastCalledWith('file', 25, expect.any(AbortSignal));
});

it('reports history failures and provides a refresh control', async () => {
  vi.mocked(api.versions).mockRejectedValue(new Error('File not found'));
  show(); expect(await screen.findByRole('alert')).toHaveTextContent('File not found');
  expect(screen.getByRole('button', { name: 'Refresh versions' })).toBeEnabled();
});

it('requires explicit history deletion confirmation and reports queued cleanup', async () => {
  vi.mocked(api.versions).mockResolvedValue({ ...page, file: { ...page.file, can_manage: true } });
  vi.spyOn(api, 'pruneVersion').mockResolvedValue({ detail: 'Version deletion queued; bytes remain counted until confirmed cleanup' });
  show(); await screen.findByText('Report.txt');
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Delete version 1' })); });
  expect(screen.getByRole('button', { name: 'Confirm history deletion' })).toBeDisabled();
  await act(async () => { await userEvent.type(screen.getByLabelText('Type DELETE to remove history'), 'DELETE'); });
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Confirm history deletion' })); });
  expect(api.pruneVersion).toHaveBeenCalledWith('file', 'old', expect.any(AbortSignal));
  expect(await screen.findByRole('status')).toHaveTextContent('bytes remain counted');
});

it('requires confirmation to apply a retention policy', async () => {
  vi.mocked(api.versions).mockResolvedValue({ ...page, file: { ...page.file, can_manage: true } });
  vi.spyOn(api, 'versionPolicy').mockResolvedValue({ ...page.file, version_keep_last: 1 });
  show(); await screen.findByText('Report.txt');
  expect(screen.getByRole('button', { name: 'Apply retention policy' })).toBeDisabled();
  await act(async () => { await userEvent.type(screen.getByLabelText('Keep newest versions'), '1'); await userEvent.type(screen.getByLabelText('Type PRUNE to apply retention'), 'PRUNE'); });
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Apply retention policy' })); });
  expect(api.versionPolicy).toHaveBeenCalledWith('file', 1, expect.any(AbortSignal));
  expect(await screen.findByRole('status')).toHaveTextContent('cannot be cancelled');
});

it('offers uploader resume/cancel controls and distinguishes cancellation from reclamation', async () => {
  vi.mocked(api.versions).mockResolvedValue({ ...page, items: [{ ...page.items[0], status: 'pending', can_complete: true, upload_method: 'multipart' }] });
  vi.spyOn(api, 'cancelVersion').mockResolvedValue({ detail: 'Cancellation recorded; storage cleanup follows the original deadline' });
  show(); await screen.findByText('Report.txt');
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Resume version 1' })); });
  expect(await screen.findByRole('status')).toHaveTextContent('Reselect the original file');
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Cancel version 1' })); });
  expect(api.cancelVersion).toHaveBeenCalledWith('file', 'old', expect.any(AbortSignal));
  expect(await screen.findByRole('status')).toHaveTextContent('original deadline');
});
