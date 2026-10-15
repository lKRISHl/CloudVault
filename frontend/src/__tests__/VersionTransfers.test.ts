import { webcrypto } from 'node:crypto';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { api, beginSessionChange, setAccessToken } from '../services/api';
import { loadVersionManifest, transferVersion } from '../features/versions/versionTransfers';
import type { VersionMultipartTicket } from '../types';

const size = 5 * 1024 * 1024; const key = 'cloudvault.version.workspace.user.file';
let file: File; let ticket: VersionMultipartTicket;
function options() { return { id: 'file', file, key, generation: 1, config: { max_bytes: 100 * 1024 * 1024, multipart_max_bytes: 1024 ** 3, multipart_part_size: size }, signal: new AbortController().signal, progress: vi.fn(), started: vi.fn() }; }
beforeEach(() => {
  setAccessToken('version-user'); vi.stubGlobal('crypto', webcrypto); sessionStorage.clear();
  file = new File([new Uint8Array(size + 1)], 'Version.bin');
  vi.spyOn(file, 'slice').mockImplementation((start = 0, end = file.size) => {
    const blob = new Blob([new Uint8Array(Math.min(end, file.size) - start)]);
    Object.defineProperty(blob, 'arrayBuffer', { value: async () => new Uint8Array(blob.size).buffer }); return blob;
  });
  vi.spyOn(api, 'startVersionMultipart').mockImplementation(async (_id, payload) => {
    ticket = { version: { id: 'version', number: 2, created_by: 'user', created_at: '', completed_at: null, status: 'pending', size_bytes: null, declared_size_bytes: file.size, checksum_sha256: null, checksum_kind: 'sha256-composite', is_current: false, can_complete: true, expires_at: '2099-01-01', upload_method: 'multipart' },
      part_size: size, parts: payload.checksums.map((checksum, index) => ({ number: index + 1, size_bytes: index ? 1 : size, checksum_sha256: checksum, confirmed: false, upload_url: `https://storage.invalid/${index + 1}`, headers: { 'x-amz-checksum-sha256': checksum } })), expires_at: '2099-01-01', can_resume: true, confirmed_bytes: 0 };
    return ticket;
  });
  vi.spyOn(api, 'confirmVersionPart').mockResolvedValue({ number: 1, size_bytes: size, checksum_sha256: '', confirmed: true, headers: {} });
  vi.spyOn(api, 'completeVersion').mockResolvedValue({ id: 'file', current_version: 2 } as Awaited<ReturnType<typeof api.completeVersion>>);
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 200 })));
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); sessionStorage.clear(); });

it('hashes chunks, sends credential-free parts and removes the resume record after verification', async () => {
  const arrayBuffer = vi.fn(); Object.defineProperty(file, 'arrayBuffer', { value: arrayBuffer });
  await transferVersion(options());
  expect(arrayBuffer).not.toHaveBeenCalled(); expect(fetch).toHaveBeenCalledTimes(2);
  expect(fetch).toHaveBeenCalledWith('https://storage.invalid/1', expect.objectContaining({ credentials: 'omit', referrerPolicy: 'no-referrer' }));
  expect(api.completeVersion).toHaveBeenCalledWith('file', 'version', expect.any(AbortSignal));
  expect(loadVersionManifest(key)).toBeNull();
});

it('keeps a secret-free manifest on interruption and resumes only unconfirmed parts after reload', async () => {
  vi.mocked(api.confirmVersionPart).mockRejectedValue(new Error('network unavailable'));
  vi.spyOn(api, 'versionPartUrl').mockRejectedValue(new Error('network unavailable'));
  await expect(transferVersion(options())).rejects.toThrow('network unavailable');
  const saved = sessionStorage.getItem(key)!; expect(saved).toContain('version'); expect(saved).not.toContain('https://'); expect(saved).not.toContain('version-user');
  expect(loadVersionManifest(key)?.versionId).toBe('version');
  const resumed = { ...ticket, parts: ticket.parts.map((part, index) => index ? part : { ...part, confirmed: true, upload_url: null }), confirmed_bytes: size };
  vi.spyOn(api, 'versionProgress').mockResolvedValue(resumed); vi.spyOn(api, 'resumeVersion').mockResolvedValue(resumed);
  vi.mocked(api.confirmVersionPart).mockResolvedValue({ ...ticket.parts[1], confirmed: true }); vi.mocked(fetch).mockClear();
  await transferVersion(options());
  expect(api.startVersionMultipart).toHaveBeenCalledTimes(1);
  expect(fetch).toHaveBeenCalledTimes(1); expect(fetch).toHaveBeenCalledWith('https://storage.invalid/2', expect.anything());
});

it('rejects another file manifest and stale sessions before storage transfer', async () => {
  const config = options();
  vi.spyOn(api, 'startVersionMultipart').mockImplementation(async () => { beginSessionChange(); throw new Error('Session changed'); });
  await expect(transferVersion(config)).rejects.toThrow('Session changed'); expect(fetch).not.toHaveBeenCalled();
  const saved = loadVersionManifest(key)!; sessionStorage.setItem(key, JSON.stringify({ ...saved, checksum: 'x'.repeat(44) }));
  await expect(transferVersion(options())).rejects.toThrow('original file'); expect(fetch).not.toHaveBeenCalled();
});

it('reconciles complete receipts during grace without requesting expired PUT grants', async () => {
  vi.mocked(api.completeVersion).mockRejectedValueOnce(new Error('completion acknowledgement lost'));
  await expect(transferVersion(options())).rejects.toThrow('acknowledgement lost');
  const ready = { ...ticket, parts: ticket.parts.map(part => ({ ...part, confirmed: true, upload_url: null })), can_resume: false, confirmed_bytes: file.size };
  vi.spyOn(api, 'versionProgress').mockResolvedValue(ready);
  const resume = vi.spyOn(api, 'resumeVersion').mockRejectedValue(new Error('PUT deadline expired'));
  vi.mocked(fetch).mockClear();
  await transferVersion(options());
  expect(resume).not.toHaveBeenCalled(); expect(fetch).not.toHaveBeenCalled();
  expect(loadVersionManifest(key)).toBeNull();
});
