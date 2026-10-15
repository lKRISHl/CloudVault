import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthContext';
import { api } from '../../services/api';

export function PermissionsPage() {
  const { kind, id = '' } = useParams(); const { user } = useAuth();
  if (kind !== 'files' && kind !== 'folders') return <p role="alert">Unknown resource type.</p>;
  return <Permissions key={`${user?.tenant?.id}:${user?.id}:${kind}:${id}`} kind={kind} id={id} />;
}

function Permissions({ kind, id }: { kind: 'files' | 'folders'; id: string }) {
  const { user } = useAuth(); const cache = useQueryClient();
  const [offset, setOffset] = useState(0); const [memberOffset, setMemberOffset] = useState(0);
  const [target, setTarget] = useState(''); const [role, setRole] = useState<'viewer' | 'editor'>('viewer');
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [message, setMessage] = useState('');
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const key = ['permissions', user?.tenant?.id, user?.id, kind, id];
  const query = useQuery({ queryKey: [...key, offset], queryFn: ({ signal }) => api.permissions(kind, id, offset, signal) });
  const members = useQuery({ queryKey: ['permission-candidates', user?.tenant?.id, user?.id, memberOffset], queryFn: () => api.members(memberOffset, 25), enabled: query.isSuccess });
  async function mutate(action: () => Promise<void>, text: string) {
    setBusy(true); setError(''); setMessage('');
    try {
      await action(); if (!alive.current) return;
      await cache.invalidateQueries({ predicate: value => ['permissions', 'files', 'folders', 'file-search', 'shares', 'folder-destination'].includes(String(value.queryKey[0])) });
      if (alive.current) setMessage(text);
    } catch (failure) { if (alive.current) setError(failure instanceof Error ? failure.message : 'Unable to update permissions'); }
    finally { if (alive.current) setBusy(false); }
  }
  function submit(event: FormEvent) { event.preventDefault(); if (target) void mutate(() => api.setGrant(kind, id, target, role), 'Member access saved. Existing external links were revoked.'); }
  return <main className="space-y-6">
    <div><p className="eyebrow">Resource access</p><h1 className="page-title">Permissions</h1><p className="page-description">Choose who can read and edit this {kind === 'files' ? 'file' : 'folder'}.</p></div>
    <Link className="secondary-button" to="/app/folders">Back to files</Link>
    {query.isPending && <p>Loading permissions…</p>}
    {query.error && <><p role="alert">{query.error.message}</p><button className="secondary-button" onClick={() => void query.refetch()}>Retry permissions</button></>}
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    {query.data && <>
      <section className="content-card p-6 space-y-4" aria-label="Resource visibility"><h2 className="text-xl font-semibold break-words">{query.data.name}</h2>
        <p>Current visibility: <strong>{query.data.visibility === 'private' ? 'Private' : 'Workspace'}</strong></p>
        <p>Creators and workspace owners/admins retain management access. Every containing folder must also be accessible.</p>
        <div className="flex flex-wrap gap-3"><button className="secondary-button" disabled={busy || query.data.visibility === 'private'} onClick={() => void mutate(() => api.setVisibility(kind, id, 'private'), 'Resource is private. Existing external links were revoked.')}>Make private</button><button className="secondary-button" disabled={busy || query.data.visibility === 'workspace'} onClick={() => void mutate(() => api.setVisibility(kind, id, 'workspace'), 'Workspace visibility enabled. Existing external links were revoked.')}>Allow workspace readers</button></div>
      </section>
      <form className="content-card p-6 space-y-4" onSubmit={submit}><h2 className="section-title">Grant member access</h2>
        <p>Viewers can read and download. Editors can also rename this resource; folder editors can create content within it. Creators and managers control permissions, moves and external links.</p>
        {members.error && <><p role="alert">{members.error.message}</p><button type="button" className="secondary-button" onClick={() => void members.refetch()}>Retry member candidates</button></>}
        <label className="block">Workspace member<select className="block border rounded p-2 w-full" required value={target} onChange={event => setTarget(event.target.value)}><option value="">Choose a member from this page</option>{members.data?.map(member => <option key={member.user_id} value={member.user_id}>{member.full_name} · {member.email}</option>)}</select></label>
        <div className="flex gap-3"><button type="button" className="secondary-button" disabled={busy || !memberOffset || members.isFetching} onClick={() => { setTarget(''); setMemberOffset(memberOffset - 25); }}>Previous members</button><button type="button" className="secondary-button" disabled={busy || members.isFetching || members.data?.length !== 25} onClick={() => { setTarget(''); setMemberOffset(memberOffset + 25); }}>Next members</button></div>
        <label className="block">Resource role<select className="block border rounded p-2 w-full" value={role} onChange={event => setRole(event.target.value as 'viewer' | 'editor')}><option value="viewer">Viewer</option><option value="editor">Editor</option></select></label>
        <button className="primary-button" disabled={busy || !target}>Save member access</button>
      </form>
      <section className="space-y-3" aria-label="Explicit grants"><h2 className="section-title">Explicit access</h2><ul className="content-card divide-y">{query.data.items.map(grant => <li className="p-4 space-y-2" key={grant.user_id}><p className="break-all">{members.data?.find(member => member.user_id === grant.user_id)?.full_name ?? grant.user_id} · {grant.role}</p><button className="secondary-button" disabled={busy} onClick={() => void mutate(() => api.setGrant(kind, id, grant.user_id, null), 'Explicit grant removed. Workspace visibility and creator/manager rights still apply.')}>Remove access {grant.user_id.slice(0, 8)}</button></li>)}</ul>{query.data.items.length === 0 && <p>No explicit grants.</p>}<div className="flex gap-3"><button className="secondary-button" disabled={busy || !offset || query.isFetching} onClick={() => setOffset(offset - 25)}>Previous grants</button><button className="secondary-button" disabled={busy || !query.data.has_more || offset >= 10000 || query.isFetching} onClick={() => setOffset(offset + 25)}>Next grants</button></div></section>
      <p className="text-sm text-gray-500">Private folders protect descendants. A direct grant cannot bypass a private ancestor; grant access to each required ancestor separately. Grants affect this resource, with no inherited editor role. Removing a grant does not deny workspace visibility. Permission changes revoke external links for the affected file or folder subtree; previously issued storage URLs remain usable until expiry.</p>
    </>}
  </main>;
}
