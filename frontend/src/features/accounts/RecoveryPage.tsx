import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../../services/api';

export function RecoveryPage() {
  const [email, setEmail] = useState('');
  const [purpose, setPurpose] = useState<'reset' | 'verify'>('reset');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); setPending(true); setError(''); setMessage('');
    try { setMessage((await api.requestRecovery(email, purpose)).detail); }
    catch (err) { setError(err instanceof Error ? err.message : 'Unable to request email'); }
    finally { setPending(false); }
  }
  return <main className="max-w-md mx-auto p-6 space-y-4">
    <h1 className="text-2xl font-semibold">Recover or verify your account</h1>
    {message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}
    <form onSubmit={submit} className="space-y-4">
      <label className="block">Email<input className="block border rounded p-2 w-full" type="email" required
        value={email} onChange={(event) => setEmail(event.target.value)} /></label>
      <label className="block">Email purpose<select className="block border rounded p-2 w-full" value={purpose}
        onChange={(event) => setPurpose(event.target.value as 'reset' | 'verify')}>
        <option value="reset">Reset password</option><option value="verify">Verify email</option>
      </select></label>
      <button className="border rounded px-4 py-2" disabled={pending}>Request email</button>
    </form>
    <Link to="/login" className="text-blue-600 underline">Back to sign in</Link>
  </main>;
}
