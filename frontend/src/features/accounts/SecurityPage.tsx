import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { api } from '../../services/api';

export function SecurityPage() {
  const { user, clearSession } = useAuth(); const cache = useQueryClient();
  const [password, setPassword] = useState(''); const [email, setEmail] = useState('');
  const [confirmation, setConfirmation] = useState(''); const [message, setMessage] = useState('');
  const [offset, setOffset] = useState(0);
  const key = ['account', user?.id];
  const sessions = useQuery({ queryKey: [...key, 'sessions', offset], queryFn: () => api.sessions(offset) });
  const deliveries = useQuery({ queryKey: [...key, 'deliveries'], queryFn: api.emailDeliveries, refetchInterval: 10000 });
  const verification = useMutation({
    mutationFn: () => api.requestRecovery(user!.email, 'verify'),
    onSuccess: async (result) => { setMessage(result.detail); await cache.invalidateQueries({ queryKey: key }); },
  });
  const change = useMutation({ mutationFn: () => api.requestEmailChange(email, password),
    onSuccess: async (result) => { setMessage(result.detail); setPassword(''); await cache.invalidateQueries({ queryKey: key }); } });
  const revoke = useMutation({ mutationFn: api.revokeSession,
    onSuccess: async (_, id) => { if (sessions.data?.find((item) => item.id === id)?.current) clearSession();
      else await cache.invalidateQueries({ queryKey: [...key, 'sessions'] }); } });
  const signOut = useMutation({ mutationFn: () => api.signOutAll(password), onSuccess: clearSession });
  const deletion = useMutation({ mutationFn: () => api.deleteAccount(password, confirmation), onSuccess: clearSession });
  const errors = [sessions.error, deliveries.error, verification.error, change.error, revoke.error, signOut.error, deletion.error].filter(Boolean);
  const submit = (event: FormEvent, action: () => void) => { event.preventDefault(); setMessage(''); action(); };
  return <main className="max-w-3xl mx-auto p-6 space-y-6">
    <Link className="text-blue-600 underline" to="/app">Back to workspace</Link>
    <h1 className="text-2xl font-semibold">Account security and email</h1>
    <p>{user?.email} · {user?.email_verified ? 'Verified' : 'Email not verified'}</p>
    {message && <p role="status">{message}</p>}
    {errors.map((error, index) => <p role="alert" key={index}>{error instanceof Error ? error.message : 'Request failed'}</p>)}
    {!user?.email_verified && <button className="border rounded px-4 py-2" disabled={verification.isPending}
      onClick={() => verification.mutate()}>Resend verification email</button>}
    <label className="block">Current password<input className="block border rounded p-2" type="password"
      value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" /></label>
    <section className="space-y-3"><h2 className="text-lg font-semibold">Change email</h2>
      <form onSubmit={(event) => submit(event, () => change.mutate())} className="space-y-3">
        <label className="block">New email<input className="block border rounded p-2" type="email" required
          value={email} onChange={(event) => setEmail(event.target.value)} /></label>
        <button className="border rounded px-4 py-2" disabled={!user?.email_verified || !password || change.isPending}>Request email change</button>
      </form><p>Your address changes only after you verify the new email. All sessions will then be revoked.</p>
    </section>
    <section className="space-y-3"><h2 className="text-lg font-semibold">Active sessions</h2>
      {sessions.isPending && <p>Loading sessions…</p>}
      <ul>{sessions.data?.map((item) => <li key={item.id} className="border rounded p-3 flex gap-3 items-center">
        <span className="flex-1">{item.current ? 'This session' : 'Other session'} · {new Date(item.created_at).toLocaleString()}</span>
        <button className="border rounded px-3 py-2" disabled={revoke.isPending} aria-label={`Revoke session ${item.id}`}
          onClick={() => revoke.mutate(item.id)}>Revoke</button>
      </li>)}</ul>
      <button className="border rounded px-3 py-2" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>Previous sessions</button>
      <button className="border rounded px-3 py-2" disabled={sessions.data?.length !== 25} onClick={() => setOffset(offset + 25)}>Next sessions</button>
      <button className="border rounded px-3 py-2" disabled={!password || signOut.isPending} onClick={() => signOut.mutate()}>Sign out all devices</button>
    </section>
    <section className="space-y-3"><h2 className="text-lg font-semibold">Recent email delivery</h2>
      <p>Queued means delivery is still pending. Sent means the mail server accepted the message.</p>
      <ul>{deliveries.data?.map((item) => <li key={item.id}>{item.purpose} · {item.state} · attempts: {item.attempts}</li>)}</ul>
    </section>
    <section className="space-y-3"><h2 className="text-lg font-semibold">Delete account</h2>
      <p>Deletion removes your profile and access. Organization owners must transfer ownership first. Ownership transfer is not available yet.</p>
      <form onSubmit={(event) => submit(event, () => deletion.mutate())} className="space-y-3">
        <label className="block">Type DELETE to confirm<input className="block border rounded p-2" required
          value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /></label>
        <button className="border rounded px-4 py-2" disabled={confirmation !== 'DELETE' || !password || deletion.isPending}>Delete my account</button>
      </form>
    </section>
  </main>;
}
