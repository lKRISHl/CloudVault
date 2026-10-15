import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthContext';
import { api } from '../../services/api';

export function DestinationPicker({ title, busy, choose, cancel, action = 'Move here' }: {
  title: string; busy: boolean; choose: (id: string | null) => void; cancel: () => void; action?: string;
}) {
  const { user } = useAuth();
  const [parent, setParent] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const query = useQuery({ queryKey: ['folder-destination', user?.tenant?.id, user?.id, title, parent, offset], queryFn: ({ signal }) => api.folders(parent, offset, signal) });
  function browse(id: string | null) { setParent(id); setOffset(0); }
  return <section role="dialog" aria-label={title} className="border rounded-xl p-4 space-y-3">
    <h3 className="font-semibold">{title}</h3>
    <p>Destination: All folders{query.data?.breadcrumbs.map(item => ` / ${item.name}`).join('')}</p>
    <button className="secondary-button" disabled={busy} onClick={() => browse(null)}>Destination root</button>
    {query.data?.parent && <button className="secondary-button" disabled={busy} onClick={() => browse(query.data!.parent!.parent_id)}>Destination up</button>}
    {query.error && <><p role="alert">{query.error.message}</p><button className="secondary-button" disabled={busy || query.isFetching} onClick={() => void query.refetch()}>Retry destination</button></>}
    {query.isPending && <p>Loading destination…</p>}
    <ul>{query.data?.items.map(item => <li key={item.id}><button className="secondary-button" disabled={busy} onClick={() => browse(item.id)} aria-label={`Open destination ${item.name}`}>{item.name}</button></li>)}</ul>
    <button className="secondary-button" disabled={busy || !offset || query.isFetching} onClick={() => setOffset(offset - 25)}>Previous destinations</button>
    <button className="secondary-button" disabled={busy || !query.data?.has_more || query.isFetching} onClick={() => setOffset(offset + 25)}>Next destinations</button>
    <p>Choose a writable destination. Containing folders govern access; existing permissions stay attached.</p>
    <button className="secondary-button" disabled={busy || query.isFetching || !query.data || (!!parent && !query.data.parent?.can_write)} onClick={() => choose(parent)}>{action}</button>
    <button className="secondary-button" disabled={busy} onClick={cancel}>Cancel destination</button>
  </section>;
}
