import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api } from '../../services/api';

export function TrashButton({ kind, id, name }: { kind: 'files' | 'folders'; id: string; name: string }) {
  const cache = useQueryClient(); const alive = useRef(true);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const [cancelUploads, setCancelUploads] = useState(false); const [confirmation, setConfirmation] = useState('');
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  async function move(cancel = false) {
    setBusy(true); setError('');
    try {
      if (cancel) await api.cancelUploadsAndTrash(id, confirmation); else await api.moveToTrash(kind, id);
      if (!alive.current) return;
      setCancelUploads(false); setConfirmation('');
      await cache.invalidateQueries({ predicate: query => ['trash', 'files', 'folders', 'file-search', 'shares', 'permissions'].includes(String(query.queryKey[0])) });
    } catch (failure) { if (alive.current) setError(failure instanceof Error ? failure.message : 'Unable to move to trash'); }
    finally { if (alive.current) setBusy(false); }
  }
  return <span className="inline-block"><button className="secondary-button" disabled={busy} onClick={() => void move()}>Move {name} to trash</button>{error && <span role="alert">{error}</span>}
    {kind === 'folders' && <button className="secondary-button" disabled={busy} onClick={() => { setCancelUploads(!cancelUploads); setConfirmation(''); }}>Cancel uploads and trash {name}</button>}
    {cancelUploads && <span role="dialog" aria-label={`Cancel uploads and trash ${name}`} className="block space-y-3 border rounded p-4">
      <span className="block">This cancels all tracked pending original upload records in the live folder subtree, including other creators' uploads when you are a workspace manager, and moves it to trash atomically. Restoring does not resume cancelled uploads. Stored bytes and outstanding URLs wait for safe cleanup; completed files remain recoverable. At most 100 pending uploads per operation.</span>
      <label className="block">Type CANCEL UPLOADS to continue<input className="block border rounded p-2" value={confirmation} onChange={event => setConfirmation(event.target.value)} /></label>
      <button className="secondary-button" disabled={busy || confirmation !== 'CANCEL UPLOADS'} onClick={() => void move(true)}>Confirm cancellation and trash</button>
      <button className="secondary-button" disabled={busy} onClick={() => setCancelUploads(false)}>Keep uploads</button>
    </span>}
  </span>;
}
