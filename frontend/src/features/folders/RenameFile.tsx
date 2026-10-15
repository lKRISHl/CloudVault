import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api } from '../../services/api';

export function RenameFile({ id, name }: { id: string; name: string }) {
  const [open, setOpen] = useState(false); const [value, setValue] = useState(name);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  const cache = useQueryClient(); const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try { await api.renameFile(id, value); if (alive.current) { setOpen(false); await cache.invalidateQueries({ predicate: query => ['files', 'file-search', 'shares', 'permissions'].includes(String(query.queryKey[0])) }); } }
    catch (failure) { if (alive.current) setError(failure instanceof Error ? failure.message : 'Rename failed'); }
    finally { if (alive.current) setBusy(false); }
  }
  return <span className="inline-block ml-3">{!open ? <button className="secondary-button" onClick={() => { setValue(name); setError(''); setOpen(true); }}>Rename file {name}</button> : <form onSubmit={submit} className="flex flex-wrap gap-3"><label>New filename<input className="block border rounded p-2" required maxLength={255} value={value} onChange={event => setValue(event.target.value)} /></label><button className="secondary-button" disabled={busy}>Save filename</button><button type="button" className="secondary-button" disabled={busy} onClick={() => setOpen(false)}>Cancel filename</button></form>}{error && <span role="alert">{error}</span>}</span>;
}
