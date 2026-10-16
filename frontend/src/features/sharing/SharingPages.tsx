import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthContext';
import { AuthLayout } from '../../components/AuthLayout';
import { api, publicShareRequest } from '../../services/api';
import type { SharedFile } from '../../types';

export function ShareManagementPage() {
  const { user } = useAuth();
  const { fileId = '' } = useParams();
  return <ShareManager key={`${user?.tenant?.id}:${user?.id}:${fileId}`} fileId={fileId} />;
}

function ShareManager({ fileId }: { fileId: string }) {
  const { user } = useAuth();
  const cache = useQueryClient();
  const [offset, setOffset] = useState(0);
  const key = ['shares', user?.tenant?.id, user?.id, fileId];
  const query = useQuery({ queryKey: [...key, offset], queryFn: ({ signal }) => api.shares(fileId, offset, signal) });
  const [hours, setHours] = useState('24');
  const [password, setPassword] = useState('');
  const [allow, setAllow] = useState(true);
  const [maximum, setMaximum] = useState('');
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  async function create(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setUrl('');
    try {
      const result = await api.createShare(fileId, { expires_in_hours: Number(hours), password: password || null,
        allow_download: allow, max_downloads: maximum ? Number(maximum) : null });
      if (!alive.current) return;
      setUrl(result.share_url); setPassword(''); setOffset(0);
      await cache.invalidateQueries({ queryKey: key });
    } catch (failure) { if (alive.current) setError(failure instanceof Error ? failure.message : 'Unable to create link'); }
    finally { if (alive.current) setBusy(false); }
  }
  async function revoke(id: string) {
    setBusy(true); setError('');
    try { await api.revokeShare(fileId, id); if (alive.current) { setUrl(''); await cache.invalidateQueries({ queryKey: key }); } }
    catch (failure) { if (alive.current) setError(failure instanceof Error ? failure.message : 'Unable to revoke link'); }
    finally { if (alive.current) setBusy(false); }
  }
  return <main className="space-y-6">
    <div><p className="eyebrow">External collaboration</p><h1 className="page-title">Share file</h1><p className="page-description">Give someone a time-limited link to this file. Anyone holding the link and its password can use it.</p></div>
    <Link className="secondary-button" to="/app/folders">Back to files</Link>
    {query.data && <p className="text-xl font-semibold break-words">{query.data.file_name}</p>}
    {query.error && <><p role="alert">{query.error.message}</p><button className="secondary-button" onClick={() => void query.refetch()}>Retry share links</button></>}
    {query.isPending && <p>Loading share links…</p>}
    {query.data && <form className="content-card p-6 space-y-4" onSubmit={create}>
      <h2 className="section-title">Create a share link</h2>
      <label className="block">Expires in hours<input className="block border rounded p-2 w-full" type="number" min="1" max="720" required value={hours} onChange={event => setHours(event.target.value)} /></label>
      <label className="block">Optional link password<input className="block border rounded p-2 w-full" type="password" minLength={8} maxLength={128} autoComplete="new-password" value={password} onChange={event => setPassword(event.target.value)} /></label>
      <label className="flex gap-2"><input type="checkbox" checked={allow} onChange={event => setAllow(event.target.checked)} />Allow downloads</label>
      <label className="block">Maximum download grants (optional)<input className="block border rounded p-2 w-full" type="number" min="1" max="10000" value={maximum} onChange={event => setMaximum(event.target.value)} /></label>
      <p className="text-sm text-gray-500">A grant counts each issued download URL, including retries. It does not count completed downloads. Disabling downloads shares the filename and size only.</p>
      <button className="primary-button" disabled={busy}>Create share link</button>
    </form>}
    {error && <p role="alert">{error}</p>}
    {url && <div className="content-card p-6 space-y-3"><p role="status">Link created. Save it now; it cannot be retrieved later.</p><label className="block">New share URL<input className="block border rounded p-2 w-full" readOnly value={url} onFocus={event => event.target.select()} /></label><p>Send the password separately, if you added one.</p></div>}
    <section aria-label="Share links" className="space-y-3"><h2 className="section-title">Existing links</h2>
      <ul className="content-card divide-y">{query.data?.items.map(link => <li className="p-4 space-y-2" key={link.id}>
        <p>Expires {new Date(link.expires_at).toLocaleString()} · {link.password_required ? 'Password protected' : 'No password'}</p>
        <p>{link.revoked_at ? 'Revoked' : new Date(link.expires_at) <= new Date() ? 'Expired' : 'Active'} · {link.allow_download ? 'Downloads allowed' : 'Metadata only'} · {link.download_grants} grants issued{link.max_downloads ? ` of ${link.max_downloads}` : ''}</p>
        <button className="secondary-button" disabled={busy || !!link.revoked_at} onClick={() => void revoke(link.id)}>Revoke link {link.id.slice(0, 8)}</button>
      </li>)}</ul>
      {query.data?.items.length === 0 && <p>No share links yet.</p>}
      <div className="flex gap-3"><button className="secondary-button" disabled={!offset || query.isFetching || busy} onClick={() => setOffset(offset - 25)}>Previous links</button><button className="secondary-button" disabled={!query.data?.has_more || query.isFetching || busy || offset >= 10000} onClick={() => setOffset(offset + 25)}>Next links</button></div>
    </section>
    <p className="text-sm text-gray-500">Revocation blocks new grants. Already issued storage URLs work until expiry. Only successfully scanned content can be shared; scanning does not guarantee safety. Removing a publisher or changing their role revokes their links.</p>
  </main>;
}

export function PublicSharePage() {
  const [token, setToken] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get('token') ?? '');
  const [password, setPassword] = useState('');
  const [file, setFile] = useState<SharedFile | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const abort = useRef<AbortController | null>(null);
  useEffect(() => {
    // Remove the capability from address/history after taking it into component memory.
    const clearFragment = () => window.history.replaceState(window.history.state, '', window.location.pathname + window.location.search);
    const adoptLink = () => {
      const next = new URLSearchParams(window.location.hash.slice(1)).get('token');
      if (next !== null) {
        abort.current?.abort(); setToken(next); setPassword(''); setFile(null); setError(''); setBusy(false); clearFragment();
      }
    };
    clearFragment(); window.addEventListener('hashchange', adoptLink);
    return () => { abort.current?.abort(); window.removeEventListener('hashchange', adoptLink); };
  }, []);
  async function access(event: FormEvent) {
    event.preventDefault(); abort.current?.abort(); const controller = new AbortController(); abort.current = controller;
    setBusy(true); setError(''); setFile(null);
    try { const result = await publicShareRequest<SharedFile>('access', { token, password }, controller.signal); if (!controller.signal.aborted) setFile(result); }
    catch (failure) { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : 'Share unavailable'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  async function download() {
    abort.current?.abort(); const controller = new AbortController(); abort.current = controller;
    setBusy(true); setError('');
    try {
      const result = await publicShareRequest<{ download_url: string; name: string }>('download-url', { token, password }, controller.signal);
      if (controller.signal.aborted) return;
      const link = document.createElement('a'); link.href = result.download_url; link.download = result.name;
      link.referrerPolicy = 'no-referrer'; link.rel = 'noopener noreferrer'; document.body.append(link);
      try { link.click(); } finally { link.remove(); }
      setFile(current => current ? { ...current, grants_remaining: current.grants_remaining === null ? null : Math.max(0, current.grants_remaining - 1), allow_download: current.allow_download && current.grants_remaining !== 1 } : null);
    } catch (failure) { if (!controller.signal.aborted) { setFile(null); setError(failure instanceof Error ? failure.message : 'Download unavailable'); } }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <AuthLayout><div className="w-full max-w-md space-y-4 auth-form">
    <p className="eyebrow">CloudVault sharing</p><h1 className="text-2xl font-semibold">A file shared with you</h1>
    <p>Open the link to check access. Enter its password if the sender provided one.</p>
    {!token && <p role="alert">Open the complete share link supplied by the sender.</p>}
    <form onSubmit={access} className="space-y-4"><label className="block">Link password<input className="block border rounded p-2 w-full" type="password" maxLength={128} autoComplete="off" value={password} onChange={event => { setPassword(event.target.value); setFile(null); }} /></label><button className="primary-button" disabled={busy || !token}>Open shared file</button></form>
    {error && <p role="alert">{error}</p>}
    {file && <section aria-label="Shared file" className="space-y-3"><h2 className="text-xl font-semibold break-words">{file.name}</h2><p>{file.size_bytes.toLocaleString()} bytes · Scan complete; no safety guarantee</p><p>Expires {new Date(file.expires_at).toLocaleString()}</p>{file.allow_download ? <button className="primary-button" disabled={busy} onClick={() => void download()}>Download shared file</button> : <p>Downloads disabled or grant limit reached.</p>}{file.grants_remaining !== null && <p>{file.grants_remaining} download grants remaining</p>}</section>}
    <Link className="text-blue-600 underline" to="/login">Sign in to CloudVault</Link>
  </div></AuthLayout>;
}
