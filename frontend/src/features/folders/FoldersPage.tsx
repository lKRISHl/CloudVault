import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { api } from '../../services/api';
import type { Folder } from '../../types';

const button = 'border rounded px-3 py-2 disabled:opacity-50';
const input = 'block border rounded p-2 w-full';

function MoveDestination({ folder, pending, choose, cancel }: {
  folder: Folder; pending: boolean; choose: (parent: string | null) => void; cancel: () => void;
}) {
  const { user } = useAuth();
  const [parent, setParent] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const query = useQuery({ queryKey: ['folder-destination', user?.tenant?.id, user?.id, folder.id, parent, offset], queryFn: () => api.folders(parent, offset) });
  const forbidden = query.data?.breadcrumbs.some((item) => item.id === folder.id);
  function browse(id: string | null) { setParent(id); setOffset(0); }
  return <section role="dialog" aria-label="Move folder" className="bg-white border rounded-xl p-5 space-y-3">
    <h2 className="text-lg font-semibold">Move {folder.name}</h2>
    <p>Destination: All folders{query.data?.breadcrumbs.map((item) => ` / ${item.name}`).join('')}</p>
    <button className={button} disabled={pending} onClick={() => browse(null)}>Destination root</button>
    {query.data?.parent && <button className={button} disabled={pending} onClick={() => browse(query.data!.parent!.parent_id)}>Destination up</button>}
    {query.error && <p role="alert">{query.error instanceof Error ? query.error.message : 'Unable to load destination'}</p>}
    {query.error && <button className={button} disabled={query.isFetching} onClick={() => void query.refetch()}>Retry destination</button>}
    {query.isPending && <p>Loading destination…</p>}
    <ul>{query.data?.items.map((item) => <li key={item.id} className="p-2">
      <button className={button} disabled={pending || item.id === folder.id} aria-label={`Open destination ${item.name}`} onClick={() => browse(item.id)}>{item.name}</button>
    </li>)}</ul>
    <button className={button} disabled={!offset || query.isFetching || pending} onClick={() => setOffset(Math.max(0, offset - 25))}>Previous destinations</button>
    <button className={button} disabled={!query.data?.has_more || query.isFetching || pending} onClick={() => setOffset(offset + 25)}>Next destinations</button>
    <p>Choose a writable destination. A folder cannot be moved inside itself or its descendants.</p>
    <button className={button} disabled={pending || query.isFetching || !query.data || !!forbidden || (!!parent && !query.data.parent?.can_write)} onClick={() => choose(parent)}>Move here</button>
    <button className={button} disabled={pending} onClick={cancel}>Cancel move</button>
  </section>;
}

export function FoldersPage() {
  const { user } = useAuth();
  const cache = useQueryClient();
  const [params, setParams] = useSearchParams();
  const parent = params.get('folder');
  const offset = Math.max(0, Number(params.get('offset')) || 0);
  const [name, setName] = useState('');
  const [editName, setEditName] = useState('');
  const [selected, setSelected] = useState<Folder | null>(null);
  const [mode, setMode] = useState<'rename' | 'move' | null>(null);
  const [message, setMessage] = useState('');
  const enabled = !!user?.tenant && user.email_verified;
  const key = ['folders', user?.tenant?.id, user?.id];
  const query = useQuery({ queryKey: [...key, parent, offset], queryFn: () => api.folders(parent, offset), enabled });
  async function refresh(text: string) { await cache.invalidateQueries({ queryKey: key }); setMessage(text); }
  const create = useMutation({ mutationFn: () => api.createFolder(name, parent), onSuccess: async () => { setName(''); await refresh('Folder created.'); } });
  const rename = useMutation({ mutationFn: () => api.renameFolder(selected!.id, editName), onSuccess: async () => { setSelected(null); setMode(null); await refresh('Folder renamed.'); } });
  const move = useMutation({ mutationFn: (destination: string | null) => api.moveFolder(selected!.id, destination), onSuccess: async () => { setSelected(null); setMode(null); await refresh('Folder moved.'); } });
  const errors = [query.error, create.error, rename.error, move.error].filter(Boolean);
  function open(folder: Folder, next: 'rename' | 'move') { setSelected(folder); setEditName(folder.name); setMode(next); setMessage(''); create.reset(); rename.reset(); move.reset(); }
  function browse(id: string | null) { setSelected(null); setMode(null); setMessage(''); setParams(id ? { folder: id } : {}); }
  const submit = (event: FormEvent, action: () => void) => { event.preventDefault(); setMessage(''); action(); };
  const writable = enabled && (!parent || query.data?.parent?.can_write);
  return <main className="max-w-4xl mx-auto p-6 space-y-6">
    <Link to="/app" className="text-blue-600 underline">Back to workspace</Link>
    <h1 className="text-2xl font-semibold">Folders</h1>
    <p>Workspace: {user?.tenant?.name ?? 'No workspace selected'}</p>
    <p>Workspace members can browse. Folder creators, owners and admins can organize folders.</p>
    {!enabled && <p role="alert">Select a workspace and verify your email in account security to use folders.</p>}
    <nav aria-label="Folder breadcrumbs" className="flex flex-wrap gap-2">
      <button className={button} onClick={() => browse(null)}>All folders</button>
      {query.data?.breadcrumbs.map((item) => <button key={item.id} className={button} onClick={() => browse(item.id)}>{item.name}</button>)}
    </nav>
    {message && <p role="status">{message}</p>}
    {errors.map((error, index) => <p role="alert" key={index}>{error instanceof Error ? error.message : 'Folder request failed'}</p>)}
    {query.error && <button className={button} disabled={query.isFetching} onClick={() => void query.refetch()}>Retry folders</button>}
    {query.isPending && enabled && <p>Loading folders…</p>}
    {writable && <form onSubmit={(event) => submit(event, () => create.mutate())} className="border rounded-xl p-5 bg-white space-y-3">
      <label className="block">Folder name<input className={input} required maxLength={255} value={name} onChange={(event) => setName(event.target.value)} /></label>
      <button className={button} disabled={create.isPending}>Create folder</button>
    </form>}
    <ul className="border rounded divide-y bg-white">{query.data?.items.map((item) => <li key={item.id} className="p-4 flex flex-wrap gap-3 items-center">
      <button className="flex-1 text-left text-blue-600 underline" aria-label={`Open folder ${item.name}`} onClick={() => browse(item.id)}>{item.name}</button>
      {item.can_write ? <>
        <button className={button} aria-label={`Rename ${item.name}`} onClick={() => open(item, 'rename')}>Rename</button>
        <button className={button} aria-label={`Move ${item.name}`} onClick={() => open(item, 'move')}>Move</button>
      </> : <span>Read only</span>}
    </li>)}</ul>
    {query.data?.items.length === 0 && <p>No folders here.</p>}
    <button className={button} disabled={!offset || query.isFetching} onClick={() => setParams({ ...(parent ? { folder: parent } : {}), offset: String(Math.max(0, offset - 25)) })}>Previous folders</button>
    <button className={button} disabled={!query.data?.has_more || query.isFetching} onClick={() => setParams({ ...(parent ? { folder: parent } : {}), offset: String(offset + 25) })}>Next folders</button>
    {selected && mode === 'rename' && <section role="dialog" aria-label="Rename folder" className="border rounded-xl p-5 bg-white space-y-3">
      <h2 className="text-lg font-semibold">Rename {selected.name}</h2>
      <form onSubmit={(event) => submit(event, () => rename.mutate())} className="space-y-3">
        <label className="block">New folder name<input className={input} required maxLength={255} value={editName} onChange={(event) => setEditName(event.target.value)} /></label>
        <button className={button} disabled={rename.isPending}>Save rename</button>
        <button type="button" className={button} disabled={rename.isPending} onClick={() => setMode(null)}>Cancel rename</button>
      </form>
    </section>}
    {selected && mode === 'move' && <MoveDestination folder={selected} pending={move.isPending} choose={(id) => move.mutate(id)} cancel={() => setMode(null)} />}
  </main>;
}
