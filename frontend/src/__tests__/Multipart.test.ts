import { webcrypto } from 'node:crypto';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { api, beginSessionChange, setAccessToken, uploadMultipartFile } from '../services/api';
import type { FileMetadata, MultipartProgress, MultipartTicket } from '../types';

const size = 5 * 1024 * 1024;
const signal = () => new AbortController().signal;
let selected: File;
let ticket: MultipartTicket;
beforeEach(() => {
  setAccessToken('multipart-test');
  vi.stubGlobal('crypto', webcrypto);
  selected = new File([new Uint8Array(size + 1)], 'Chunks.bin');
  // jsdom does not implement Blob.arrayBuffer; preserve bounded slice semantics.
  vi.spyOn(selected, 'slice').mockImplementation((start = 0, end = selected.size) => {
    const blob = new Blob([new Uint8Array(Math.min(end, selected.size) - start)]);
    Object.defineProperty(blob, 'arrayBuffer', { value: async () => new Uint8Array(blob.size).buffer });
    return blob;
  });
  vi.spyOn(api, 'startMultipart').mockImplementation(async payload => {
    ticket = { file: { id: 'multipart-id', status: 'pending', declared_size_bytes: selected.size } as FileMetadata,
      part_size: size, expires_at: '2030-01-01', parts: payload.checksums.map((checksum, index) => ({
        number: index + 1, size_bytes: index ? 1 : size, checksum_sha256: checksum, confirmed: false,
        upload_url: `https://storage.example/part/${index + 1}`, headers: { 'x-amz-checksum-sha256': checksum },
      })) };
    return ticket;
  });
  vi.spyOn(api, 'confirmPart').mockResolvedValue({ number: 1, size_bytes: size, checksum_sha256: '', confirmed: true, headers: {} });
  vi.spyOn(api, 'multipartPartUrl').mockImplementation(async (_id, number) => ticket.parts[number - 1]);
  vi.spyOn(api, 'completeMultipart').mockImplementation(async () => {
    const binary = Uint8Array.from(ticket.parts.flatMap(part => [...atob(part.checksum_sha256)].map(char => char.charCodeAt(0))));
    const hash = new Uint8Array(await webcrypto.subtle.digest('SHA-256', binary));
    return { ...ticket.file, status: 'uploaded', checksum_kind: 'sha256-composite', size_bytes: selected.size,
      checksum_sha256: btoa(String.fromCharCode(...hash)) };
  });
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200 }));
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('hashes bounded chunks, transfers without account credentials and verifies composite completion', async () => {
  const started = vi.fn();
  expect((await uploadMultipartFile(selected, null, 'request', size, size * 2, signal(), vi.fn(), started)).status).toBe('uploaded');
  expect(started).toHaveBeenCalledWith('multipart-id');
  expect(selected.slice).toHaveBeenCalledWith(0, size);
  expect(selected.slice).toHaveBeenCalledWith(size, size * 2);
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(fetch).toHaveBeenCalledWith('https://storage.example/part/1', expect.objectContaining({ method: 'PUT', credentials: 'omit', referrerPolicy: 'no-referrer' }));
  expect(api.confirmPart).toHaveBeenCalledTimes(2);
});

it('reconciles lost part acknowledgements without resending confirmed bytes', async () => {
  vi.mocked(fetch).mockRejectedValue(new TypeError('Acknowledgement lost'));
  expect((await uploadMultipartFile(selected, null, 'request', size, size * 2, signal(), vi.fn())).status).toBe('uploaded');
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(api.multipartPartUrl).not.toHaveBeenCalled();
});

it('bounds failed-part retries and leaves the file incomplete', async () => {
  vi.mocked(fetch).mockResolvedValue({ ok: false, status: 503 } as Response);
  vi.mocked(api.confirmPart).mockRejectedValue(new Error('Part missing'));
  await expect(uploadMultipartFile(selected, null, 'request', size, size * 2, signal(), vi.fn())).rejects.toThrow('Part transfer failed');
  expect(fetch).toHaveBeenCalledTimes(3);
  expect(api.multipartPartUrl).toHaveBeenCalledTimes(2);
  expect(api.completeMultipart).not.toHaveBeenCalled();
});

it('skips previously confirmed parts when retrying the same manifest', async () => {
  const original = vi.mocked(api.startMultipart).getMockImplementation()!;
  vi.mocked(api.startMultipart).mockImplementation(async (...args) => {
    const result = await original(...args); result.parts[0].confirmed = true; result.parts[0].upload_url = null; return result;
  });
  await uploadMultipartFile(selected, null, 'request', size, size * 2, signal(), vi.fn());
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(api.confirmPart).toHaveBeenCalledWith('multipart-id', 2, expect.any(AbortSignal));
});

it('rejects changed declarations before sending any bytes', async () => {
  const original = vi.mocked(api.startMultipart).getMockImplementation()!;
  vi.mocked(api.startMultipart).mockImplementation(async (...args) => {
    const result = await original(...args); result.parts[0].size_bytes--; return result;
  });
  await expect(uploadMultipartFile(selected, null, 'request', size, size * 2, signal(), vi.fn())).rejects.toThrow('Invalid upload part');
  expect(fetch).not.toHaveBeenCalled();
});

it('fails closed on a workspace change after initiation', async () => {
  const original = vi.mocked(api.startMultipart).getMockImplementation()!;
  vi.mocked(api.startMultipart).mockImplementation(async (...args) => { const result = await original(...args); beginSessionChange(); return result; });
  await expect(uploadMultipartFile(selected, null, 'request', size, size * 2, signal(), vi.fn())).rejects.toThrow('Session changed');
  expect(fetch).not.toHaveBeenCalled();
});

it('rejects oversize or cancelled transfers before initiation', async () => {
  await expect(uploadMultipartFile(selected, null, 'request', size, 1, signal(), vi.fn())).rejects.toThrow('limits');
  const controller = new AbortController(); controller.abort();
  await expect(uploadMultipartFile(selected, null, 'request', size, size * 2, controller.signal, vi.fn())).rejects.toThrow('Upload stopped');
  expect(api.startMultipart).not.toHaveBeenCalled();
});

it('resumes an existing session using its original chunk size and only missing parts', async () => {
  const original = vi.mocked(api.startMultipart).getMockImplementation()!;
  vi.spyOn(api, 'multipartProgress').mockResolvedValue({ file: { declared_size_bytes: selected.size }, part_size: size } as MultipartProgress);
  vi.spyOn(api, 'resumeMultipart').mockImplementation(async (_id, checksums) => {
    const result = await original({ name: selected.name, folder_id: null, declared_size_bytes: selected.size,
      declared_content_type: null, request_id: 'existing', part_size: size, checksums });
    result.parts[0].confirmed = true; result.parts[0].upload_url = null;
    return result;
  });
  await uploadMultipartFile(selected, null, 'unused-new-request', size * 2, size * 2, signal(), vi.fn(), undefined, 'multipart-id');
  expect(api.startMultipart).not.toHaveBeenCalled();
  expect(api.resumeMultipart).toHaveBeenCalledWith('multipart-id', expect.arrayContaining([expect.any(String)]), expect.any(AbortSignal));
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(selected.slice).toHaveBeenCalledWith(0, size);
});

it('rejects a different-sized reselected file and stale progress without transfer', async () => {
  vi.spyOn(api, 'multipartProgress').mockResolvedValue({ file: { declared_size_bytes: 1 }, part_size: size } as MultipartProgress);
  await expect(uploadMultipartFile(selected, null, 'request', size, size * 2, signal(), vi.fn(), undefined, 'existing')).rejects.toThrow('original file');
  vi.mocked(api.multipartProgress).mockImplementation(async () => { beginSessionChange(); return { file: { declared_size_bytes: selected.size }, part_size: size } as MultipartProgress; });
  await expect(uploadMultipartFile(selected, null, 'request', size, size * 2, signal(), vi.fn(), undefined, 'existing')).rejects.toThrow('Session changed');
  expect(fetch).not.toHaveBeenCalled();
});
