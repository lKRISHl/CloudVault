import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { api } from '../../services/api';

export function TrashPage() {
  const { user } = useAuth();
  return <Trash key={`${user?.tenant?.id}:${user?.id}`} />;
}

function Trash() {
  const { user } = useAuth(); const cache = useQueryClient();
  const [offset, setOffset] = useState(0); const [busy, setBusy] = useState(false);
  const [error, setError] = useState(''); const [message, setMessage] = useState('');
  const [selected, setSelected] = useState<string | null>(null); const [confirmation, setConfirmation] = useState('');
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const query = useQuery({ queryKey: ['trash', user?.tenant?.id, user?.id, offset], queryFn: ({ signal }) => api.trash(offset, signal) });
  async function mutate(id: string, purge = false) {
    setBusy(true); setError(''); setMessage('');
    try {
      if (purge) await api.purgeTrash(id, confirmation); else await api.restoreTrash(id);
      if (!alive.current) return;
      setSelected(null); setConfirmation('');
      await cache.invalidateQueries({ predicate: entry => ['trash', 'files', 'folders', 'file-search', 'shares', 'permissions', 'folder-destination'].includes(String(entry.queryKey[0])) });
      if (alive.current) setMessage(purge ? 'Permanent deletion queued. Restoration is disabled; storage cleanup may take time.' : 'Restored with its original permissions. Older independent trash stays in trash.');
    } catch (failure) { if (alive.current) setError(failure instanceof Error ? failure.message : 'Trash operation failed'); }
    finally { if (alive.current) setBusy(false); }
  }
  return <main className="space-y-6"><div><p className="eyebrow">Recover your work</p><h1 className="page-title">Trash</h1><p className="page-description">Restore content within 30 days, or queue permanent deletion.</p></div>
    <Link className="secondary-button" to="/app/folders">Back to files</Link>
    <p>Creators and workspace managers can manage trash when its containing folders are readable. Moving to trash and restoring also require a writable original parent. Restore the parent first and resolve active name conflicts.</p>
    <p className="text-sm text-gray-500">Permanent folder deletion includes nested trash. It cannot be undone once queued. Stored bytes are removed after outstanding upload authorizations expire and storage confirms removal; internal cleanup references are retained. Previously downloaded bytes cannot be recalled.</p>
    {message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}
    {query.error && <p role="alert">{query.error.message}</p>}
    <button className="secondary-button" disabled={busy || query.isFetching} onClick={() => void query.refetch()}>Refresh trash</button>
    {query.isPending && <p>Loading trash…</p>}
    <ul className="content-card divide-y">{query.data?.items.map(item => <li key={item.id} className="p-5 space-y-3">
      <h2 className="font-semibold break-words">{item.name}</h2><p>{item.kind === 'files' ? 'File' : 'Folder'} · Trashed {new Date(item.trashed_at).toLocaleString()}</p>
      <p>Retained until {new Date(item.retain_until).toLocaleString()}</p>
      {item.purge_requested_at && <p>Permanent deletion queued. Cleanup may take time.</p>}
      <div className="flex flex-wrap gap-3"><button className="secondary-button" disabled={busy || !!item.purge_requested_at || new Date(item.retain_until) <= new Date()} onClick={() => void mutate(item.id)}>Restore {item.name}</button>
      <button className="secondary-button" disabled={busy || !!item.purge_requested_at} onClick={() => { setSelected(item.id); setConfirmation(''); }}>Delete permanently {item.name}</button></div>
      {selected === item.id && <section role="dialog" aria-label={`Permanently delete ${item.name}`} className="space-y-3 border rounded p-4"><p>This permanently deletes the file or folder subtree, including independently trashed descendants. Restoration will be disabled immediately. Cleanup starts no earlier than {new Date(item.not_before).toLocaleString()}.</p><label className="block">Type DELETE to permanently delete<input className="block border rounded p-2 w-full" value={confirmation} onChange={event => setConfirmation(event.target.value)} /></label><button className="secondary-button" disabled={busy || confirmation !== 'DELETE'} onClick={() => void mutate(item.id, true)}>Confirm permanent deletion</button><button className="secondary-button" disabled={busy} onClick={() => setSelected(null)}>Cancel permanent deletion</button></section>}
    </li>)}</ul>
    {query.data?.items.length === 0 && <p>No manageable items in trash.</p>}
    <div className="flex gap-3"><button className="secondary-button" disabled={busy || query.isFetching || !offset} onClick={() => setOffset(offset - 25)}>Previous trash</button><button className="secondary-button" disabled={busy || query.isFetching || !query.data?.has_more || offset >= 10000} onClick={() => setOffset(offset + 25)}>Next trash</button></div>
  </main>;
}
