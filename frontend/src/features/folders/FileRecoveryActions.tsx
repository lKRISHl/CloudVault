import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api } from '../../services/api';
import type { FileMetadata } from '../../types';
import { DestinationPicker } from './DestinationPicker';

export function FileRecoveryActions({ file }: { file: FileMetadata }) {
  const cache = useQueryClient(); const alive = useRef(true);
  const [open, setOpen] = useState(false); const [busy, setBusy] = useState(false);
  const [confirmation, setConfirmation] = useState(''); const [error, setError] = useState('');
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  async function perform(destination: string | null) {
    setBusy(true); setError('');
    try {
      if (file.legacy_metadata) await api.discardMetadata(file.id, confirmation);
      else await api.moveFile(file.id, destination, file.folder_id);
      if (!alive.current) return;
      setOpen(false);
      await cache.invalidateQueries({ predicate: query => ['files', 'file-search', 'folders', 'versions', 'shares', 'permissions'].includes(String(query.queryKey[0])) });
    } catch (failure) { if (alive.current) setError(failure instanceof Error ? failure.message : 'File operation failed'); }
    finally { if (alive.current) setBusy(false); }
  }
  return <div className="space-y-2">
    <button className="secondary-button" disabled={busy} onClick={() => { setOpen(!open); setConfirmation(''); }}>{file.legacy_metadata ? `Discard metadata ${file.name}` : `Move ${file.name}`}</button>
    {error && <p role="alert">{error}</p>}
    {open && (file.legacy_metadata ? <section role="dialog" aria-label={`Discard metadata ${file.name}`}>
      <p>This legacy record has no upload session or verified stored content. Discard it to release its name, then upload a new file. Internal metadata is retained.</p>
      <label>Type DISCARD to discard metadata<input className="block border rounded p-2" value={confirmation} onChange={event => setConfirmation(event.target.value)} /></label>
      <button className="secondary-button" disabled={busy || confirmation !== 'DISCARD'} onClick={() => void perform(null)}>Confirm metadata discard</button>
      <button className="secondary-button" disabled={busy} onClick={() => setOpen(false)}>Cancel discard</button>
    </section> : <><p>Moving revokes external links and changes which containing folders protect this file.</p><DestinationPicker title={`Move file ${file.name}`} busy={busy} choose={id => void perform(id)} cancel={() => setOpen(false)} /></>)}
  </div>;
}
