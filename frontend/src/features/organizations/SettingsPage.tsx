import { useEffect, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { api } from '../../services/api';

const inputClass = 'block w-full border border-slate-300 rounded p-2';
const buttonClass = 'border rounded px-3 py-2 disabled:opacity-50';

export function SettingsPage() {
  const { user, reloadUser } = useAuth();
  const cache = useQueryClient();
  const [fullName, setFullName] = useState(user?.full_name ?? '');
  const [orgName, setOrgName] = useState(user?.tenant.name ?? '');
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<'admin' | 'member'>('member');
  const [offset, setOffset] = useState(0);
  const [invitationOffset, setInvitationOffset] = useState(0);
  const [link, setLink] = useState('');
  const [message, setMessage] = useState('');
  const verified = user?.email_verified === true;
  const manager = verified && (user?.role === 'owner' || user?.role === 'admin');
  const key = ['organization', user?.tenant.id, user?.id];
  const members = useQuery({
    queryKey: [...key, 'members', offset], queryFn: () => api.members(offset), enabled: !!user && verified,
  });
  const invitations = useQuery({
    queryKey: [...key, 'invitations', invitationOffset],
    queryFn: () => api.invitations(invitationOffset), enabled: !!user && manager,
  });

  useEffect(() => {
    setFullName(user?.full_name ?? '');
    setOrgName(user?.tenant.name ?? '');
  }, [user]);

  async function refresh() {
    await cache.invalidateQueries({ queryKey: key });
    await reloadUser();
  }
  const profile = useMutation({
    mutationFn: () => api.updateProfile(fullName),
    onSuccess: async () => { await refresh(); setMessage('Profile saved.'); },
  });
  const organization = useMutation({
    mutationFn: () => api.renameOrganization(orgName),
    onSuccess: async () => { await refresh(); setMessage('Organization saved.'); },
  });
  const invitation = useMutation({
    mutationFn: () => api.invite(email, role),
    onSuccess: async (created) => {
      setLink(`${window.location.origin}/join#token=${encodeURIComponent(created.token)}`);
      setEmail('');
      await cache.invalidateQueries({ queryKey: [...key, 'invitations'] });
    },
  });
  const changeRole = useMutation({
    mutationFn: ({ id, nextRole }: { id: string; nextRole: 'admin' | 'member' }) => api.changeRole(id, nextRole),
    onSuccess: refresh,
  });
  const remove = useMutation({ mutationFn: api.removeMember, onSuccess: refresh });
  const revoke = useMutation({ mutationFn: api.revokeInvitation, onSuccess: refresh });
  const errors = [members.error, manager ? invitations.error : null, profile.error,
    organization.error, invitation.error, changeRole.error, remove.error, revoke.error].filter(Boolean);

  function submit(event: FormEvent, action: () => void) {
    event.preventDefault();
    setMessage('');
    action();
  }

  return <main className="min-h-screen bg-slate-50 p-6">
    <div className="max-w-3xl mx-auto space-y-8">
      <Link to="/app" className="text-blue-600 underline">Back to workspace</Link>
      <h1 className="text-2xl font-semibold">Profile and organization</h1>
      <Link to="/app/security" className="block text-blue-600 underline">Account security and email</Link>
      {!verified && <p role="alert">Verify your email in account security before using organization features.</p>}
      {message && <p role="status">{message}</p>}
      {errors.map((error, index) => <p role="alert" className="text-red-700" key={index}>
        {error instanceof Error ? error.message : 'Unable to complete request'}
      </p>)}
      <section className="bg-white border rounded-xl p-5 space-y-3">
        <h2 className="text-lg font-semibold">Your profile</h2>
        <p>{user?.email} · {user?.role}</p>
        <form className="space-y-3" onSubmit={(event) => submit(event, () => profile.mutate())}>
          <label className="block">Full name
            <input className={inputClass} required maxLength={120} value={fullName}
              onChange={(event) => setFullName(event.target.value)} />
          </label>
          <button disabled={profile.isPending} className={buttonClass}>Save profile</button>
        </form>
      </section>
      <section className="bg-white border rounded-xl p-5 space-y-3">
        <h2 className="text-lg font-semibold">Organization</h2>
        {manager ? <form className="space-y-3" onSubmit={(event) => submit(event, () => organization.mutate())}>
          <label className="block">Organization name
            <input className={inputClass} required maxLength={120} value={orgName}
              onChange={(event) => setOrgName(event.target.value)} />
          </label>
          <button disabled={organization.isPending} className={buttonClass}>Save organization</button>
        </form> : <p>{user?.tenant.name}</p>}
      </section>
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Members</h2>
        {verified && members.isPending && <p>Loading members…</p>}
        <ul className="divide-y border rounded bg-white">
          {members.data?.map((member) => <li key={member.user_id} className="p-4 flex flex-wrap items-center gap-3">
            <div className="flex-1"><p className="font-medium">{member.full_name}</p><p>{member.email}</p></div>
            {user?.role === 'owner' && member.role !== 'owner' ?
              <select aria-label={`Role for ${member.email}`} value={member.role}
                disabled={changeRole.isPending} className="border rounded p-2"
                onChange={(event) => changeRole.mutate({
                  id: member.user_id, nextRole: event.target.value as 'admin' | 'member',
                })}>
                <option value="member">Member</option><option value="admin">Admin</option>
              </select> : <span>{member.role}</span>}
            {manager && member.role !== 'owner' && member.user_id !== user?.id &&
              (user?.role === 'owner' || member.role === 'member') &&
              <button disabled={remove.isPending} className={buttonClass}
                aria-label={`Remove ${member.email}`} onClick={() => {
                  if (window.confirm(`Remove ${member.email}? Their account will lose access.`)) {
                    remove.mutate(member.user_id);
                  }
                }}>Remove</button>}
          </li>)}
        </ul>
        <div className="flex gap-3">
          <button className={buttonClass} disabled={offset === 0 || members.isFetching}
            onClick={() => setOffset(Math.max(0, offset - 25))}>Previous members</button>
          <button className={buttonClass} disabled={members.data?.length !== 25 || members.isFetching}
            onClick={() => setOffset(offset + 25)}>Next members</button>
        </div>
      </section>
      {manager && <section className="bg-white border rounded-xl p-5 space-y-4">
        <h2 className="text-lg font-semibold">Invite someone</h2>
        <p>Invite someone new to CloudVault. Share their private link; it expires in seven days.</p>
        <form className="space-y-3" onSubmit={(event) => submit(event, () => invitation.mutate())}>
          <label className="block">Invitation email
            <input className={inputClass} type="email" required value={email}
              onChange={(event) => setEmail(event.target.value)} />
          </label>
          {user?.role === 'owner' && <label className="block">Invitation role
            <select className={inputClass} value={role}
              onChange={(event) => setRole(event.target.value as 'admin' | 'member')}>
              <option value="member">Member</option><option value="admin">Admin</option>
            </select>
          </label>}
          <button className={buttonClass} disabled={invitation.isPending}>Create invitation</button>
        </form>
        {link && <label className="block">Private invitation link
          <input className={inputClass} readOnly value={link} onClick={(event) => event.currentTarget.select()} />
        </label>}
        <h3 className="font-medium">Pending invitations</h3>
        {invitations.isPending && <p>Loading invitations…</p>}
        {invitations.data?.length === 0 && <p>No pending invitations.</p>}
        <ul className="space-y-2">{invitations.data?.map((item) =>
          <li key={item.id} className="flex flex-wrap items-center gap-3">
            <span className="flex-1">{item.email} · {item.role}</span>
            <button className={buttonClass} disabled={revoke.isPending}
              aria-label={`Revoke invitation for ${item.email}`} onClick={() => revoke.mutate(item.id)}>Revoke</button>
          </li>)}</ul>
        <div className="flex gap-3">
          <button className={buttonClass} disabled={invitationOffset === 0 || invitations.isFetching}
            onClick={() => setInvitationOffset(Math.max(0, invitationOffset - 25))}>Previous invitations</button>
          <button className={buttonClass} disabled={invitations.data?.length !== 25 || invitations.isFetching}
            onClick={() => setInvitationOffset(invitationOffset + 25)}>Next invitations</button>
        </div>
      </section>}
    </div>
  </main>;
}
