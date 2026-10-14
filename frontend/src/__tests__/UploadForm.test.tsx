import { webcrypto } from 'node:crypto';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { UploadForm } from '../features/folders/UploadForm';
import { api, beginSessionChange, setAccessToken, uploadBrowserFile, ApiRequestError } from '../services/api';

vi.mock('../auth/AuthContext', () => ({ useAuth: () => ({ user: { id: 'creator', tenant: { id: 'workspace' } } }) }));
const metadata = { id: 'file-id', name: 'Sample.txt', tenant_id: 'workspace', folder_id: null, created_by: 'creator',
  declared_size_bytes: 6, declared_content_type: 'text/plain', status: 'pending' as const, created_at: '', updated_at: '', can_write: true };
const ticket = { file: metadata, upload_url: 'https://storage.example/object?signature=private',
  headers: { 'Content-Type': 'application/octet-stream', 'If-None-Match': '*', 'x-amz-checksum-sha256': 'checksum' }, expires_at: '2030-01-01' };
function file() {
  const selected = new File(['sample'], 'Sample.txt', { type: 'text/plain' });
  Object.defineProperty(selected, 'arrayBuffer', { value: async () => new TextEncoder().encode('sample').buffer });
  return selected;
}
function show(retryId: string | null = null) {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <UploadForm folderId={null} retryId={retryId} finished={() => {}} />
  </QueryClientProvider>);
}
beforeEach(() => {
  setAccessToken('unit-upload-token');
  vi.stubGlobal('crypto', webcrypto);
  vi.spyOn(api, 'uploadConfiguration').mockResolvedValue({ enabled: true, max_bytes: 104857600 });
  vi.spyOn(api, 'startUpload').mockResolvedValue(ticket);
  vi.spyOn(api, 'completeUpload').mockResolvedValue({ ...metadata, status: 'uploaded', size_bytes: 6 });
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200 }));
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('Basic upload', () => {
  it('hashes, transfers directly without account credentials and verifies completion', async () => {
    show(); const user = userEvent.setup();
    const picker = await screen.findByLabelText('File to upload');
    await waitFor(() => expect(picker).toBeEnabled());
    await act(async () => { await user.upload(picker, file()); });
    await act(async () => { await user.click(screen.getByRole('button', { name: 'Upload file' })); });
    expect(await screen.findByRole('status')).toHaveTextContent('File uploaded and verified');
    expect(api.startUpload).toHaveBeenCalledWith(expect.objectContaining({ name: 'Sample.txt', declared_size_bytes: 6,
      checksum_sha256: 'ryvb4aqbbsHireHWlPQfxxqDHQJo6YkVYhE9imKt0b8=' }));
    expect(fetch).toHaveBeenCalledWith(ticket.upload_url, expect.objectContaining({ method: 'PUT', credentials: 'omit', referrerPolicy: 'no-referrer', headers: ticket.headers }));
    expect(api.completeUpload).toHaveBeenCalledWith('file-id');
  });

  it('rejects oversized files before hashing or initiation', async () => {
    vi.mocked(api.uploadConfiguration).mockResolvedValue({ enabled: true, max_bytes: 5 });
    show(); const user = userEvent.setup();
    const picker = await screen.findByLabelText('File to upload');
    await waitFor(() => expect(picker).toBeEnabled());
    await act(async () => { await user.upload(picker, file()); });
    await act(async () => { await user.click(screen.getByRole('button', { name: 'Upload file' })); });
    expect(await screen.findByRole('alert')).toHaveTextContent('size limit');
    expect(api.startUpload).not.toHaveBeenCalled();
  });

  it('reconciles a lost storage acknowledgement through completion', async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError('Network interrupted'));
    const result = await uploadBrowserFile(file(), null, 'request', null, new AbortController().signal, () => {});
    expect(result.status).toBe('uploaded');
  });

  it('accepts an overwrite precondition response only after completion verification', async () => {
    vi.mocked(fetch).mockResolvedValue({ ok: false, status: 412 } as Response);
    expect((await uploadBrowserFile(file(), null, 'request', null, new AbortController().signal, () => {})).status).toBe('uploaded');
    expect(api.completeUpload).toHaveBeenCalledWith('file-id');
  });

  it('retries a pending record with the original checksum and keeps server errors visible', async () => {
    vi.mocked(api.completeUpload).mockRejectedValueOnce(new ApiRequestError('Object missing', 409));
    vi.spyOn(api, 'retryUpload').mockResolvedValue(ticket);
    await uploadBrowserFile(file(), null, 'request', 'file-id', new AbortController().signal, () => {});
    expect(api.retryUpload).toHaveBeenCalledWith('file-id', expect.any(String));
    expect(api.startUpload).not.toHaveBeenCalled();
  });

  it('stops after a workspace change before sending object bytes', async () => {
    vi.mocked(api.startUpload).mockImplementation(async () => { beginSessionChange(); return ticket; });
    await expect(uploadBrowserFile(file(), null, 'request', null, new AbortController().signal, () => {})).rejects.toThrow('workspace change');
    expect(fetch).not.toHaveBeenCalled();
    expect(api.completeUpload).not.toHaveBeenCalled();
  });

  it('retries loading upload settings after a network failure', async () => {
    vi.mocked(api.uploadConfiguration).mockRejectedValueOnce(new Error('Unavailable'));
    show(); const user = userEvent.setup();
    expect(await screen.findByRole('alert')).toHaveTextContent('Unable to load upload settings');
    await act(async () => { await user.click(screen.getByRole('button', { name: 'Retry upload settings' })); });
    await waitFor(() => expect(screen.getByLabelText('File to upload')).toBeEnabled());
  });

  it('rejects the wrong chosen content when reconciling an already completed upload', async () => {
    vi.mocked(api.completeUpload).mockResolvedValue({ ...metadata, status: 'uploaded', size_bytes: 6, checksum_sha256: 'different-checksum' });
    await expect(uploadBrowserFile(file(), null, 'request', 'file-id', new AbortController().signal, () => {})).rejects.toThrow('same file content');
    expect(api.startUpload).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
  });
});
