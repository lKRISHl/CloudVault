import { useState, type FormEvent } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { api } from '../../services/api';

export function AccountActionPage() {
  const location = useLocation();
  const parameters = new URLSearchParams(location.hash.slice(1));
  const purpose = parameters.get('purpose'); const token = parameters.get('token');
  const { user, reloadUser, clearSession } = useAuth();
  const [password, setPassword] = useState(''); const [confirm, setConfirm] = useState('');
  const [message, setMessage] = useState(''); const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  const valid = token && ['verify', 'reset', 'email_change'].includes(purpose ?? '');
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!token) return;
    if (purpose === 'reset' && password !== confirm) { setError('Passwords must match'); return; }
    setPending(true); setError('');
    try {
      const result = purpose === 'verify' ? await api.verifyEmail(token)
        : purpose === 'reset' ? await api.resetPassword(token, password)
          : await api.confirmEmailChange(token, password);
      if (purpose === 'verify' && user) {
        try { await reloadUser(); } catch { clearSession(); }
      }
      if (purpose !== 'verify') clearSession();
      window.history.replaceState({}, '', '/account/action');
      setPassword(''); setConfirm('');
      setMessage(result.detail);
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to complete account action'); }
    finally { setPending(false); }
  }
  return <main className="max-w-md mx-auto p-6 space-y-4">
    <h1 className="text-2xl font-semibold">{purpose === 'reset' ? 'Reset password' : purpose === 'email_change' ? 'Confirm email change' : 'Verify email'}</h1>
    {message ? <p role="status">{message}</p> : !valid ? <p role="alert">This account link is incomplete.</p>
      : purpose === 'email_change' && !user ? <p>Sign in to the account that requested this change.
        <Link className="text-blue-600 underline" to="/login" state={{ returnTo: location.pathname + location.hash }}> Sign in</Link></p>
        : <form onSubmit={submit} className="space-y-4">
          {error && <p role="alert">{error}</p>}
          {purpose !== 'verify' && <label className="block">{purpose === 'reset' ? 'New password' : 'Current password'}
            <input className="block border rounded p-2 w-full" type="password" required
              minLength={purpose === 'reset' ? 8 : 1} maxLength={128} value={password}
              onChange={(event) => setPassword(event.target.value)} /></label>}
          {purpose === 'reset' && <label className="block">Confirm new password
            <input className="block border rounded p-2 w-full" type="password" required value={confirm}
              onChange={(event) => setConfirm(event.target.value)} /></label>}
          <button className="border rounded px-4 py-2" disabled={pending}>
            {purpose === 'verify' ? 'Verify email' : purpose === 'reset' ? 'Reset password' : 'Confirm email change'}
          </button>
        </form>}
    <Link to={user ? '/app/security' : '/login'} className="text-blue-600 underline">{user ? 'Account security' : 'Sign in'}</Link>
    <Link to="/account/recover" className="block text-blue-600 underline">Request another email</Link>
  </main>;
}
