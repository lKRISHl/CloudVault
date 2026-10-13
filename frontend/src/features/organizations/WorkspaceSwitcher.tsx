import { useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { api } from '../../services/api';

export function WorkspaceSwitcher() {
  const { user, switchWorkspace, createWorkspace } = useAuth();
  const [name, setName] = useState('');
  const [offset, setOffset] = useState(0);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const workspaces = useQuery({ queryKey: ['workspaces', user?.id, user?.tenant?.id, offset],
    queryFn: () => api.workspaces(offset), enabled: user?.email_verified === true });
  async function run(action: () => Promise<void>) {
    setPending(true); setError('');
    try { await action(); setName(''); setOffset(0); }
    catch (err) { setError(err instanceof Error ? err.message : 'Unable to change workspace'); }
    finally { setPending(false); }
  }
  const create = (event: FormEvent) => { event.preventDefault(); void run(() => createWorkspace(name)); };
  if (!user?.email_verified) return <p>Verify your email in <Link to="/app/security" className="underline">account security</Link> to manage workspaces.</p>;
  return <section className="border rounded-xl bg-white p-5 space-y-3">
    <h2 className="text-lg font-semibold">Your workspaces</h2>
    {user.tenant && <p>Current workspace: {user.tenant.name}</p>}
    {!user.tenant && <p>You have no active workspace. Create one or accept an invitation.</p>}
    {(error || workspaces.error) && <p role="alert">{error || (workspaces.error instanceof Error ? workspaces.error.message : 'Unable to load workspaces')}</p>}
    {workspaces.isPending && <p>Loading workspaces…</p>}
    <ul className="space-y-2">{workspaces.data?.map((item) => <li key={item.tenant.id} className="flex gap-3 items-center">
      <span className="flex-1">{item.tenant.name} · {item.role}</span>
      {item.tenant.id === user.tenant?.id ? <span>Current workspace</span> :
        <button className="border rounded px-3 py-2" disabled={pending} aria-label={`Switch to ${item.tenant.name}`}
          onClick={() => void run(() => switchWorkspace(item.tenant.id))}>Switch</button>}
    </li>)}</ul>
    <button disabled={!offset || pending} onClick={() => setOffset(Math.max(0, offset - 25))}>Previous workspaces</button>
    <button disabled={workspaces.data?.length !== 25 || pending} onClick={() => setOffset(offset + 25)}>Next workspaces</button>
    <form onSubmit={create} className="space-y-2">
      <label className="block">New workspace name<input className="block border rounded p-2 w-full" required maxLength={120}
        value={name} onChange={(event) => setName(event.target.value)} /></label>
      <button className="border rounded px-3 py-2" disabled={pending}>Create another workspace</button>
    </form>
  </section>;
}
