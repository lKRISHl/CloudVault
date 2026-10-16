import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthContext';
import { api } from '../../services/api';
import { useLiveResource } from '../../realtime/RealtimeProvider';

export function PermissionsPage() {
  const { kind, id = '' } = useParams(); const { user } = useAuth();
  if (kind !== 'files' && kind !== 'folders') return <p role="alert">Unknown resource type.</p>;
  return <Permissions key={`${user?.tenant?.id}:${user?.id}:${kind}:${id}`} kind={kind} id={id} />;
}

function Permissions({ kind, id }: { kind: 'files' | 'folders'; id: string }) {
  const { user } = useAuth(); const cache = useQueryClient();
  const [offset, setOffset] = useState(0); const [memberOffset, setMemberOffset] = useState(0);
  const [groupSearch, setGroupSearch] = useState(''); const [groupOffset, setGroupOffset] = useState(0); const [groupTarget, setGroupTarget] = useState('');
  const [search, setSearch] = useState('');
  const [target, setTarget] = useState(''); const [role, setRole] = useState<'viewer' | 'editor'>('viewer');
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [message, setMessage] = useState('');
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const key = ['permissions', user?.tenant?.id, user?.id, kind, id];
  useLiveResource({ kind: 'permissions', resource_kind: kind, resource_id: id, offset }, [...key, offset]);
  useLiveResource({ kind: 'members', offset: memberOffset }, ['permission-candidates', user?.tenant?.id, user?.id, kind, id, search, memberOffset]);
  const query = useQuery({ queryKey: [...key, offset], queryFn: ({ signal }) => api.permissions(kind, id, offset, signal) });
  const members = useQuery({ queryKey: ['permission-candidates', user?.tenant?.id, user?.id, kind, id, search, memberOffset], queryFn: ({ signal }) => api.permissionCandidates(kind, id, search, memberOffset, signal), enabled: query.isSuccess });
  const groups = useQuery({ queryKey: ['permission-groups', user?.tenant?.id, user?.id, kind, id, groupSearch, groupOffset], queryFn: ({ signal }) => api.groups(groupSearch, groupOffset, signal), enabled: query.isSuccess, refetchInterval: 15000 });
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
        <p>Resource owners and workspace owners/admins retain management access. Every containing folder must also be accessible.</p>
        <div className="flex flex-wrap gap-3"><button className="secondary-button" disabled={busy || query.data.visibility === 'private'} onClick={() => void mutate(() => api.setVisibility(kind, id, 'private'), 'Resource is private. Existing external links were revoked.')}>Make private</button><button className="secondary-button" disabled={busy || query.data.visibility === 'workspace'} onClick={() => void mutate(() => api.setVisibility(kind, id, 'workspace'), 'Workspace visibility enabled. Existing external links were revoked.')}>Allow workspace readers</button></div>
      </section>
      <form className="content-card p-6 space-y-4" onSubmit={submit}><h2 className="section-title">Grant member access</h2>
        <p>Viewers can read and download. Editors can also rename this resource; folder editors can create content within it. Resource owners and managers control permissions, moves and external links.</p>
        {members.error && <><p role="alert">{members.error.message}</p><button type="button" className="secondary-button" onClick={() => void members.refetch()}>Retry member candidates</button></>}
        <label className="block">Search members by name or email<input className="block border rounded p-2 w-full" type="search" maxLength={100} value={search} onChange={event => { setSearch(event.target.value); setMemberOffset(0); setTarget(''); }} /></label>
        <label className="block">Workspace member<select className="block border rounded p-2 w-full" required value={target} onChange={event => setTarget(event.target.value)}><option value="">Choose a member from this page</option>{members.data?.items.map(member => <option key={member.user_id} value={member.user_id}>{member.full_name} · {member.email}</option>)}</select></label>
        <div className="flex gap-3"><button type="button" className="secondary-button" disabled={busy || !memberOffset || members.isFetching} onClick={() => { setTarget(''); setMemberOffset(memberOffset - 25); }}>Previous members</button><button type="button" className="secondary-button" disabled={busy || members.isFetching || !members.data?.has_more || memberOffset >= 10000} onClick={() => { setTarget(''); setMemberOffset(memberOffset + 25); }}>Next members</button></div>
        <label className="block">Resource role<select className="block border rounded p-2 w-full" value={role} onChange={event => setRole(event.target.value as 'viewer' | 'editor')}><option value="viewer">Viewer</option><option value="editor">Editor</option></select></label>
        <button className="primary-button" disabled={busy || !target}>Save member access</button>
      </form>
      <form className="content-card p-6 space-y-4" onSubmit={event => { event.preventDefault(); if (groupTarget) void mutate(() => api.setGroupGrant(kind, id, groupTarget, role), 'Group access saved. Existing external links were revoked.'); }}><h2 className="section-title">Grant group access</h2>
        <p>Groups use the viewer/editor role selected above. Grants combine with individual access; every ancestor still needs access and editor roles do not inherit.</p>
        {groups.error && <p role="alert">{groups.error.message}</p>}
        <label className="block">Search workspace groups<input className="block border rounded p-2 w-full" maxLength={100} value={groupSearch} onChange={event => { setGroupSearch(event.target.value); setGroupOffset(0); setGroupTarget(''); }} /></label>
        <label className="block">Workspace group<select className="block border rounded p-2 w-full" required value={groupTarget} onChange={event => setGroupTarget(event.target.value)}><option value="">Choose a group</option>{groups.data?.items.map(group => <option key={group.id} value={group.id}>{group.name}</option>)}</select></label>
        <button className="secondary-button" type="button" disabled={busy || !groupOffset || groups.isFetching} onClick={() => { setGroupTarget(''); setGroupOffset(groupOffset - 25); }}>Previous group candidates</button><button className="secondary-button" type="button" disabled={busy || !groups.data?.has_more || groupOffset >= 10000 || groups.isFetching} onClick={() => { setGroupTarget(''); setGroupOffset(groupOffset + 25); }}>Next group candidates</button>
        <button className="primary-button" disabled={busy || !groupTarget}>Save group access</button>
        <ul className="space-y-3">{query.data.group_items?.map(grant => <li key={grant.group_id}><span className="break-words">{grant.name} � {grant.role}</span> <button className="secondary-button" type="button" disabled={busy} onClick={() => void mutate(() => api.setGroupGrant(kind, id, grant.group_id, null), 'Group grant removed. Other access paths still apply.')}>Remove access for group {grant.name}</button></li>)}</ul>
      </form>
      <section className="content-card p-6 space-y-4" aria-label="Resource ownership"><h2 className="section-title">Transfer ownership</h2>
        <p>Current owner: {query.data.owner_name || query.data.owner_id}. Select a verified member above. Transfer affects this resource only and requires their access to every containing folder. Existing grants stay; external links are revoked. Upload and version attribution stays with the original creator. The previous owner keeps only their workspace role, workspace visibility and explicit or group grants.</p>
        <button className="secondary-button" disabled={busy || !target || target === query.data.owner_id} onClick={() => void mutate(() => api.transferResource(kind, id, target), 'Resource ownership transferred. Existing external links were revoked.')}>Transfer ownership to selected member</button>
      </section>
      <section className="space-y-3" aria-label="Explicit grants"><h2 className="section-title">Explicit access</h2><ul className="content-card divide-y">{query.data.items.map(grant => <li className="p-4 space-y-2" key={grant.user_id}><p className="break-all">{grant.full_name || grant.user_id} / {grant.email} / {grant.role}</p><button className="secondary-button" disabled={busy} onClick={() => void mutate(() => api.setGrant(kind, id, grant.user_id, null), 'Explicit grant removed. Workspace visibility and owner/manager rights still apply.')}>Remove access {grant.user_id.slice(0, 8)}</button></li>)}</ul>{query.data.items.length === 0 && <p>No explicit grants.</p>}<div className="flex gap-3"><button className="secondary-button" disabled={busy || !offset || query.isFetching} onClick={() => setOffset(offset - 25)}>Previous grants</button><button className="secondary-button" disabled={busy || !query.data.has_more || offset >= 10000 || query.isFetching} onClick={() => setOffset(offset + 25)}>Next grants</button></div></section>
      <p className="text-sm text-gray-500">Private folders protect descendants. A direct grant cannot bypass a private ancestor; grant access to each required ancestor separately. Grants affect this resource, with no inherited editor role. Removing a grant does not deny workspace visibility. Permission changes revoke external links for the affected file or folder subtree; previously issued storage URLs remain usable until expiry.</p>
    </>}
  </main>;
}
