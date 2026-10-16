import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { PreviewPage } from '../features/previews/PreviewPage';
import { api } from '../services/api';
import type { PreviewResult } from '../types';

vi.mock('../auth/AuthContext', () => ({ useAuth: () => ({ user: { id: 'me', tenant: { id: 'tenant' } } }) }));
const result: PreviewResult = { kind: 'text', file_id: 'file', version_id: 'version', version_number: 1,
  generation: 1, name: 'Unsafe.html', detected_type: 'text/plain; charset=utf-8', scan_status: 'clean',
  image_base64: null, text: '<script>window.unwanted=true</script>', reason: null,
  width: null, height: null, page: 0, pages: 1, truncated: false };
function show(url = '/app/files/file/preview') {
  return render(<MemoryRouter initialEntries={[url]}><Routes><Route path="/app/files/:fileId/preview" element={<PreviewPage />} /></Routes></MemoryRouter>);
}
beforeEach(() => {
  vi.spyOn(api, 'preview').mockResolvedValue(result);
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:owned-preview'), revokeObjectURL: vi.fn() }));
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('renders untrusted HTML as text, with no active markup', async () => {
  const view = show();
  expect(await screen.findByLabelText('Text preview')).toHaveTextContent('<script>window.unwanted=true</script>');
  expect(view.container.querySelector('script')).toBeNull();
  expect(api.preview).toHaveBeenCalledWith('file', null, 0, expect.any(AbortSignal));
});

it('uses only a local PNG blob and revokes it when leaving', async () => {
  vi.mocked(api.preview).mockResolvedValue({ ...result, kind: 'image', image_base64: 'iVBORw0KGgo=', text: null });
  const view = show();
  const image = await screen.findByRole('img');
  expect(image).toHaveAttribute('src', 'blob:owned-preview');
  expect(image).toHaveAttribute('referrerpolicy', 'no-referrer');
  view.unmount();
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:owned-preview');
});

it('binds PDF page navigation to the selected historical version', async () => {
  vi.mocked(api.preview).mockImplementation(async (_id, _version, page) => ({ ...result, kind: 'pdf', page: page ?? 0, pages: 2, image_base64: 'iVBORw0KGgo=', text: null }));
  show('/app/files/file/preview?version=old-version');
  await screen.findByText('Page 1 of 2');
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Next PDF page' })); });
  await screen.findByText('Page 2 of 2');
  expect(api.preview).toHaveBeenLastCalledWith('file', 'old-version', 1, expect.any(AbortSignal));
  expect(screen.getByRole('button', { name: 'Next PDF page' })).toBeDisabled();
});

it('offers explicit unsupported-content fallback without embedding original bytes', async () => {
  vi.mocked(api.preview).mockResolvedValue({ ...result, kind: 'unsupported', text: null, reason: 'Video preview is not available' });
  const view = show();
  expect(await screen.findByText(/Video preview is not available/)).toHaveAttribute('role', 'status');
  expect(view.container.querySelector('iframe, object, video, embed')).toBeNull();
  expect(screen.getByRole('link', { name: 'Versions and downloads' })).toHaveAttribute('href', '/app/files/file/versions');
});

it('does not expose stale content when access fails and supports explicit retry', async () => {
  vi.mocked(api.preview).mockRejectedValueOnce(new Error('File not found')).mockResolvedValueOnce(result);
  show();
  expect(await screen.findByRole('alert')).toHaveTextContent('File not found');
  expect(screen.queryByLabelText('Text preview')).toBeNull();
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Refresh preview' })); });
  expect(await screen.findByLabelText('Text preview')).toBeVisible();
});

it('ignores a late response after leaving the scoped preview', async () => {
  let resolve!: (value: PreviewResult) => void;
  vi.mocked(api.preview).mockReturnValue(new Promise(done => { resolve = done; }));
  const view = show(); view.unmount();
  await act(async () => { resolve({ ...result, kind: 'image', image_base64: 'iVBORw0KGgo=' }); });
  expect(URL.createObjectURL).not.toHaveBeenCalled();
});

it('shows video as a static poster with an explicit original-download fallback', async () => {
  vi.mocked(api.preview).mockResolvedValue({ ...result, kind: 'video', image_base64: 'iVBORw0KGgo=', text: null });
  const view = show();
  expect(await screen.findByRole('img')).toHaveAttribute('src', 'blob:owned-preview');
  expect(screen.getByText(/Static video poster/)).toBeVisible();
  expect(view.container.querySelector('video, iframe, object')).toBeNull();
});

it('cancels a pending preview and permits a fresh request', async () => {
  vi.mocked(api.preview).mockImplementation((_id, _version, _page, signal) => new Promise((_resolve, reject) => {
    signal?.addEventListener('abort', () => reject(new DOMException('Cancelled', 'AbortError')), { once: true });
  }));
  show();
  await act(async () => { await userEvent.click(screen.getByRole('button', { name: 'Cancel preview' })); });
  expect(screen.getByRole('alert')).toHaveTextContent('Preview cancelled');
  expect(screen.getByRole('button', { name: 'Refresh preview' })).toBeEnabled();
});
