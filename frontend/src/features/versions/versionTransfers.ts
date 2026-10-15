import { api, ApiRequestError, getSessionEpoch } from '../../services/api';
import type { VersionTransferState, FileVersion } from '../../types';

export interface VersionManifest {
  requestId: string; versionId?: string; mode: 'basic' | 'multipart'; generation: number;
  size: number; name: string; type: string | null; partSize: number; checksums: string[]; checksum: string;
}
export function loadVersionManifest(key: string): VersionManifest | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(key) ?? 'null') as VersionManifest | null;
    if (!value || !['basic', 'multipart'].includes(value.mode) || !Number.isSafeInteger(value.size)
      || value.size < 0 || !Number.isSafeInteger(value.generation) || value.generation < 1
      || typeof value.requestId !== 'string' || !Array.isArray(value.checksums)
      || typeof value.name !== 'string' || value.name.length > 4096
      || (value.type !== null && typeof value.type !== 'string')
      || (value.versionId !== undefined && (typeof value.versionId !== 'string' || !/^[A-Za-z0-9-]{1,64}$/.test(value.versionId)))
      || value.checksums.length > 1024 || value.checksums.some(item => typeof item !== 'string' || item.length !== 44)
      || typeof value.checksum !== 'string' || value.checksum.length !== 44
      || (value.mode === 'multipart' && (!Number.isSafeInteger(value.partSize) || value.partSize < 5242880 || value.partSize > 33554432))) return null;
    return value;
  } catch { return null; }
}
export function forgetVersionManifest(key: string) { try { sessionStorage.removeItem(key); } catch { /* Server history remains the recovery source. */ } }

export async function transferVersion(options: {
  id: string; file: File; generation: number; key: string; config: { max_bytes: number; multipart_max_bytes?: number; multipart_part_size?: number };
  signal: AbortSignal; progress: (message: string) => void; started: (manifest: VersionManifest) => void;
  resume?: (FileVersion & VersionTransferState) | null;
}) {
  const { id, file, key, config, signal, progress, started } = options;
  const epoch = getSessionEpoch();
  const current = () => { if (signal.aborted) throw new DOMException('Upload paused', 'AbortError'); if (epoch !== getSessionEpoch()) throw new Error('Session changed; reopen version history.'); };
  let saved = options.resume ? null : loadVersionManifest(key);
  const resumeId = options.resume?.id ?? saved?.versionId;
  let mode = options.resume?.upload_method ?? saved?.mode ?? (file.size > Math.min(config.max_bytes, config.multipart_part_size ?? 8388608) ? 'multipart' : 'basic');
  let partSize = options.resume?.part_size ?? saved?.partSize ?? config.multipart_part_size ?? 8388608;
  let remoteChecksums: string[] | null = null;
  let readyForCompletion = false;
  current();
  if (resumeId && mode === 'multipart') {
    const remote = await api.versionProgress(id, resumeId, signal); current();
    if (remote.version.declared_size_bytes !== file.size) throw new Error('Reselect the original file content.');
    partSize = remote.part_size; remoteChecksums = remote.parts.map(part => part.checksum_sha256);
    readyForCompletion = remote.version.status === 'uploaded' || (remote.parts.length > 0 && remote.parts.every(part => part.confirmed));
    mode = 'multipart';
  }
  if ((mode === 'basic' && file.size > config.max_bytes && !resumeId)
    || (mode === 'multipart' && (!file.size || (!resumeId && file.size > (config.multipart_max_bytes ?? 0))
      || partSize < 5242880 || partSize > 33554432 || Math.ceil(file.size / partSize) > 1024))) throw new Error('Replacement file exceeds transfer limits.');
  const checksums: string[] = []; const digests: Uint8Array[] = [];
  const count = mode === 'multipart' ? Math.ceil(file.size / partSize) : 1;
  for (let index = 0; index < count; index++) {
    current(); progress(`Checking part ${index + 1} of ${count}…`);
    const bytes = mode === 'multipart' ? await file.slice(index * partSize, (index + 1) * partSize).arrayBuffer() : await file.arrayBuffer(); current();
    const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)); current();
    digests.push(digest); checksums.push(btoa(String.fromCharCode(...digest)));
  }
  const combined = new Uint8Array(digests.length * 32); digests.forEach((digest, index) => combined.set(digest, index * 32));
  const checksum = mode === 'basic' ? checksums[0] : btoa(String.fromCharCode(...new Uint8Array(await crypto.subtle.digest('SHA-256', combined)))); current();
  if ((saved && (saved.size !== file.size || saved.checksum !== checksum || JSON.stringify(saved.checksums) !== JSON.stringify(checksums)))
    || (remoteChecksums && JSON.stringify(remoteChecksums) !== JSON.stringify(checksums))) throw new Error('Reselect the original file content to resume.');
  saved = saved ?? { requestId: crypto.randomUUID(), versionId: resumeId, mode, generation: options.generation,
    size: file.size, name: file.name, type: /^[A-Za-z0-9!#$&^_.+-]+\/[A-Za-z0-9!#$&^_.+-]+$/.test(file.type) ? file.type : null,
    partSize, checksums, checksum };
  const remember = (versionId?: string) => {
    current(); saved!.versionId = versionId ?? saved!.versionId;
    // Only IDs/declarations/digests: no storage URL, token, password or file bytes.
    try { sessionStorage.setItem(key, JSON.stringify(saved)); } catch { /* Resume remains discoverable in server history. */ }
    started(saved!);
  };
  remember();
  if (resumeId && readyForCompletion) {
    progress('Verifying replacement…');
    const result = await api.completeVersion(id, resumeId, signal); current(); forgetVersionManifest(key); return result;
  }
  const payload = { request_id: saved.requestId, base_generation: saved.generation, declared_size_bytes: saved.size,
    declared_content_type: saved.type, checksum_sha256: saved.checksum };
  if (mode === 'basic') {
    let ticket;
    try { ticket = resumeId ? await api.retryVersion(id, resumeId, checksum, signal) : await api.startVersion(id, payload, signal); }
    catch (failure) {
      current();
      if (!resumeId || !(failure instanceof ApiRequestError) || failure.status !== 410) throw failure;
      // Correct-content retry can outlive PUT grants while completion grace still permits reconciliation.
      const result = await api.completeVersion(id, resumeId, signal); current(); forgetVersionManifest(key); return result;
    }
    current(); remember(ticket.version.id);
    if (ticket.upload_url) {
      progress('Transferring replacement…');
      try {
        const response = await fetch(ticket.upload_url, { method: 'PUT', body: file, headers: ticket.headers, credentials: 'omit', referrerPolicy: 'no-referrer', signal }); current();
        if (!response.ok && response.status !== 412) throw new Error('Version transfer failed.');
      } catch (failure) {
        current(); try { const result = await api.completeVersion(id, ticket.version.id, signal); current(); forgetVersionManifest(key); return result; } catch { throw failure; }
      }
    }
  } else {
    const ticket = resumeId ? await api.resumeVersion(id, resumeId, checksums, signal)
      : await api.startVersionMultipart(id, { ...payload, part_size: partSize, checksums }, signal); current(); remember(ticket.version.id);
    if (ticket.version.status !== 'uploaded') {
      if (ticket.part_size !== partSize || ticket.parts.length !== count) throw new Error('Multipart plan changed.');
      for (let index = 0; index < count; index++) {
        let part = ticket.parts[index]; const body = file.slice(index * partSize, (index + 1) * partSize);
        const check = () => { if (part.number !== index + 1 || part.size_bytes !== body.size || part.checksum_sha256 !== checksums[index]) throw new Error('Invalid version part declaration.'); };
        check(); if (part.confirmed) continue;
        for (let attempt = 0; attempt < 3; attempt++) {
          current(); progress(`Uploading part ${index + 1} of ${count}…`);
          let failure: unknown;
          try {
            if (!part.upload_url) throw new Error('Part authorization missing.');
            const response = await fetch(part.upload_url, { method: 'PUT', body, headers: part.headers, credentials: 'omit', referrerPolicy: 'no-referrer', signal }); current();
            if (!response.ok) throw new Error('Version part transfer failed.');
          } catch (error) { current(); failure = error; }
          try { await api.confirmVersionPart(id, ticket.version.id, part.number, signal); current(); break; }
          catch (error) { current(); if (attempt === 2) throw failure ?? error; part = await api.versionPartUrl(id, ticket.version.id, part.number, signal); current(); check(); }
        }
      }
    }
  }
  current(); progress('Verifying replacement…');
  const result = await api.completeVersion(id, saved.versionId!, signal); current(); forgetVersionManifest(key); return result;
}
