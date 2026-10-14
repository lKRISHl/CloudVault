import { AuthLayout } from '../components/AuthLayout';
import { useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login({ email, password });
      const returnTo = location.state?.returnTo;
      navigate(typeof returnTo === 'string' && (returnTo.startsWith('/account/action#') || returnTo.startsWith('/join#')) ? returnTo : '/app', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to sign in');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout>
      <div className="w-full max-w-md space-y-8">
        <div className="auth-form-heading space-y-2">
          <h1 className="text-5xl font-extrabold tracking-tight text-gray-900">
            Cloud<span className="text-blue-600">Vault</span>
          </h1>
          <p className="text-lg text-gray-500 font-light tracking-wide">
            AI-Native Cloud File Storage
          </p>
        </div>

        <form onSubmit={onSubmit} className="auth-form space-y-4">
          <h2 className="text-lg font-semibold text-gray-900">Sign in</h2>
          {error && (
            <p className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-md px-3 py-2">{error}</p>
          )}
          <label className="block space-y-1">
            <span className="text-sm text-gray-600">Email</span>
            <input
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </label>
          <label className="block space-y-1">
            <span className="text-sm text-gray-600">Password</span>
            <input
              type="password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="w-full rounded-md border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </label>
          <button
            type="submit"
            disabled={submitting}
            className="w-full bg-blue-600 text-white rounded-md py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-60"
          >
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
          <p className="text-sm text-gray-500 text-center">
            <Link to="/account/recover" className="text-blue-600 underline">Forgot password?</Link>
          </p>
          <p className="text-sm text-gray-500 text-center">
            New workspace?{' '}
            <Link to="/register" className="text-blue-600 font-medium">
              Create an account
            </Link>
          </p>
        </form>
      </div>
    </AuthLayout>
  );
}
