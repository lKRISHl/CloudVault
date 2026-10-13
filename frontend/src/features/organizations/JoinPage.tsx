import { useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { api } from '../../services/api';

export function JoinPage() {
  const { user, isLoading, acceptInvitation, switchWorkspace } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const token = new URLSearchParams(location.hash.slice(1)).get('token');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!token) return;
    setPending(true);
    setError(null);
    try {
      if (user) {
        const organization = await api.acceptExistingInvitation(token);
        await switchWorkspace(organization.id);
      } else {
        await acceptInvitation({ token, full_name: name, password });
      }
      navigate('/app', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to join organization');
    } finally {
      setPending(false);
    }
  }

  return <main className="min-h-screen bg-slate-50 flex items-center justify-center p-6">
    <div className="max-w-md w-full bg-white border rounded-xl p-6 space-y-4">
      <h1 className="text-2xl font-semibold">Join your organization</h1>
      <p>{user ? `Accept this invitation as ${user.email}. Your other memberships remain available.` : 'Create an account or sign in with the invited email.'}</p>
      {isLoading && <p>Restoring session…</p>}
      {user && !user.email_verified && <p role="alert">Verify your email in account security, then return to this invitation.</p>}
      {!token ? <p role="alert">The invitation link is incomplete. Ask your organization for a new link.</p>
        : <form onSubmit={submit} className="space-y-4">
          {error && <p role="alert" className="text-red-700">{error}</p>}
          {!user && <><label className="block">Full name
            <input className="block w-full border rounded p-2" required maxLength={120}
              value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <label className="block">Password
            <input className="block w-full border rounded p-2" type="password" required
              minLength={8} maxLength={128} autoComplete="new-password"
              value={password} onChange={(event) => setPassword(event.target.value)} />
          </label></>}
          <button disabled={pending || isLoading || (!!user && !user.email_verified)} className="bg-blue-600 text-white rounded px-4 py-2">
            {pending ? 'Joining…' : 'Join organization'}
          </button>
        </form>}
      {user ? <Link className="text-blue-600 underline" to="/app/security">Account security and email</Link> :
        <Link className="text-blue-600 underline" to="/login" state={{ returnTo: `/join${location.hash}` }}>Sign in to accept this invitation</Link>}
    </div>
  </main>;
}
