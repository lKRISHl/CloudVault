import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthContext';
import { api } from '../../services/api';

export function GroupsPage() {
  const { user } = useAuth();
  return <Groups key={`${user?.tenant?.id}:${user?.id}`} />;
}

function Groups() {
  const { user } = useAuth(); const cache = useQueryClient();
  const manager = !!user?.email_verified && ['owner', 'admin'].includes(user.role);
  const scope = [user?.tenant?.id, user?.id];
  const [name, setName] = useState(''); const [search, setSearch] = useState(''); const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<{ id: string; name: string } | null>(null);
  const [memberSearch, setMemberSearch] = useState(''); const [memberOffset, setMemberOffset] = useState(0);
  const [candidateOffset, setCandidateOffset] = useState(0); const [target, setTarget] = useState('');
  const [busy, setBusy] = useState(false); const [error, setError] = useState(''); const [message, setMessage] = useState('');
  const groups = useQuery({ queryKey: ['groups', ...scope, search, offset], queryFn: ({ signal }) => api.groups(search, offset, signal), enabled: manager, refetchInterval: 15000 });
  const members = useQuery({ queryKey: ['group-members', ...scope, selected?.id, memberSearch, memberOffset], queryFn: ({ signal }) => api.groupMembers(selected!.id, memberSearch, memberOffset, false, signal), enabled: manager && !!selected, refetchInterval: 15000 });
  const candidates = useQuery({ queryKey: ['group-candidates', ...scope, selected?.id, memberSearch, candidateOffset], queryFn: ({ signal }) => api.groupMembers(selected!.id, memberSearch, candidateOffset, true, signal), enabled: manager && !!selected, refetchInterval: 15000 });
  async function mutate(action: () => Promise<unknown>, text: string) {
    setBusy(true); setError(''); setMessage('');
    try { await action(); await cache.invalidateQueries({ predicate: query => ['groups', 'group-members', 'group-candidates', 'permissions', 'shares', 'files', 'folders', 'file-search'].includes(String(query.queryKey[0])) }); setMessage(text); }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Unable to update groups'); }
    finally { setBusy(false); }
  }
  function create(event: FormEvent) { event.preventDefault(); void mutate(async () => { const group = await api.createGroup(name); setSelected(group); setName(''); setOffset(0); }, 'Group created.'); }
  if (!manager) return <p role="alert">Workspace owner or admin required to manage groups.</p>;
  return <main className="space-y-6"><h1 className="page-title">Workspace groups</h1><Link to="/app/settings" className="secondary-button">Back to settings</Link>
    <p>Groups grant the existing viewer/editor roles on individual resources. Every containing folder must remain accessible. A group cannot grant workspace administration, ownership or external write access.</p>
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    {groups.error && <p role="alert">{groups.error.message}</p>}
    <form className="content-card p-6 space-y-3" onSubmit={create}><label className="block">New group name<input className="block border rounded p-2 w-full" required maxLength={255} value={name} onChange={event => setName(event.target.value)} /></label><button className="primary-button" disabled={busy}>Create group</button></form>
    <section className="content-card p-6 space-y-3" aria-label="Workspace groups"><label className="block">Search groups<input className="block border rounded p-2 w-full" maxLength={100} value={search} onChange={event => { setSearch(event.target.value); setOffset(0); }} /></label>
      <ul className="space-y-3">{groups.data?.items.map(group => <li key={group.id}><button className="secondary-button break-words" disabled={busy} onClick={() => { setSelected(group); setMemberSearch(''); setMemberOffset(0); setCandidateOffset(0); setTarget(''); }}>{group.name}</button></li>)}</ul>
      <button className="secondary-button" disabled={busy || !offset || groups.isFetching} onClick={() => setOffset(offset - 25)}>Previous groups</button><button className="secondary-button" disabled={busy || !groups.data?.has_more || offset >= 10000 || groups.isFetching} onClick={() => setOffset(offset + 25)}>Next groups</button>
    </section>
    {selected && <section className="content-card p-6 space-y-4" aria-label="Group membership"><h2 className="section-title break-words">{selected.name}</h2>
      <label className="block">Find group members or candidates<input className="block border rounded p-2 w-full" maxLength={100} value={memberSearch} onChange={event => { setMemberSearch(event.target.value); setMemberOffset(0); setCandidateOffset(0); setTarget(''); }} /></label>
      {members.error && <p role="alert">{members.error.message}</p>}{candidates.error && <p role="alert">{candidates.error.message}</p>}
      <form className="space-y-3" onSubmit={event => { event.preventDefault(); if (target) void mutate(() => api.setGroupMember(selected.id, target, true), 'Group member added. Affected external links were revoked.'); }}><label className="block">Add verified member<select className="block border rounded p-2 w-full" required value={target} onChange={event => setTarget(event.target.value)}><option value="">Choose a workspace member</option>{candidates.data?.items.map(member => <option key={member.user_id} value={member.user_id}>{member.full_name} · {member.email}</option>)}</select></label>
        <button className="secondary-button" type="button" disabled={busy || !candidateOffset || candidates.isFetching} onClick={() => { setTarget(''); setCandidateOffset(candidateOffset - 25); }}>Previous candidates</button><button className="secondary-button" type="button" disabled={busy || !candidates.data?.has_more || candidateOffset >= 10000 || candidates.isFetching} onClick={() => { setTarget(''); setCandidateOffset(candidateOffset + 25); }}>Next candidates</button><button className="primary-button" disabled={busy || !target}>Add group member</button></form>
      <ul className="space-y-3">{members.data?.items.map(member => <li key={member.user_id} className="break-words">{member.full_name} · {member.email} <button className="secondary-button" disabled={busy} onClick={() => void mutate(() => api.setGroupMember(selected.id, member.user_id, false), 'Group member removed. Other grants and workspace visibility still apply.')}>Remove {member.email} from group</button></li>)}</ul>
      <button className="secondary-button" disabled={busy || !memberOffset || members.isFetching} onClick={() => setMemberOffset(memberOffset - 25)}>Previous group members</button><button className="secondary-button" disabled={busy || !members.data?.has_more || memberOffset >= 10000 || members.isFetching} onClick={() => setMemberOffset(memberOffset + 25)}>Next group members</button>
      <p>Deleting this group removes all its grants. Membership and grant changes revoke affected external links; existing storage URLs last until expiry.</p><button className="secondary-button" disabled={busy} onClick={() => void mutate(async () => { await api.deleteGroup(selected.id); setSelected(null); }, 'Group and its grants deleted.')}>Delete group {selected.name}</button>
    </section>}
    <p className="muted-copy">Current bounds: 100 groups per workspace, 1,000 members and 100 resource grants per group. Production performance acceptance remains pending.</p>
  </main>;
}
