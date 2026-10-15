import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { api, uploadVersionFile } from '../../services/api';

export function VersionsPage() {
  const { fileId = '' } = useParams(); const { user } = useAuth();
  return <Versions key={`${user?.tenant?.id}:${user?.id}:${fileId}`} fileId={fileId} />;
}

function Versions({ fileId }: { fileId: string }) {
  const { user } = useAuth(); const cache = useQueryClient();
  const [offset, setOffset] = useState(0); const [busy, setBusy] = useState(false);
  const [error, setError] = useState(''); const [message, setMessage] = useState('');
  const [selected, setSelected] = useState<File | null>(null);
  const [restore, setRestore] = useState<{ id: string; number: number } | null>(null);
  const request = useRef(crypto.randomUUID()); const controller = useRef(new AbortController());
  useEffect(() => { controller.current = new AbortController(); return () => controller.current.abort(); }, []);
  const query = useQuery({ queryKey: ['versions', user?.tenant?.id, user?.id, fileId, offset], queryFn: ({ signal }) => api.versions(fileId, offset, signal) });
  const config = useQuery({ queryKey: ['version-configuration', user?.tenant?.id, user?.id], queryFn: () => api.uploadConfiguration() });
  const data = query.data;
  async function invalidate() {
    await cache.invalidateQueries({ predicate: entry => ['versions', 'files', 'file-search', 'shares'].includes(String(entry.queryKey[0])) });
  }
  async function action(operation: () => Promise<void>) {
    setBusy(true); setError(''); setMessage('');
    try { await operation(); }
    catch (failure) { if (!controller.current.signal.aborted) setError(failure instanceof Error ? failure.message : 'Version operation failed'); }
    finally { if (!controller.current.signal.aborted) setBusy(false); }
  }
  async function upload() {
    if (!selected || !data || !config.data) return;
    await action(async () => {
      await uploadVersionFile(fileId, selected, request.current, data.file.version_generation ?? 1, config.data!.max_bytes, controller.current.signal);
      if (controller.current.signal.aborted) return;
      request.current = crypto.randomUUID(); setSelected(null); await invalidate(); setMessage('Version uploaded and verified.');
    });
  }
  async function download(id: string) {
    await action(async () => {
      const ticket = await api.versionDownload(fileId, id, controller.current.signal);
      if (controller.current.signal.aborted) return;
      const link = document.createElement('a'); link.href = ticket.download_url;
      link.download = data?.file.name ?? ''; link.referrerPolicy = 'no-referrer'; link.rel = 'noopener noreferrer';
      document.body.append(link); try { link.click(); } finally { link.remove(); }
    });
  }
  return <main className="space-y-6">
    <header className="page-heading"><div><p className="eyebrow">File history</p><h1>Versions</h1><p>{data?.file.name ?? 'Retained content and current version'}</p></div><Link className="secondary-button" to={`/app/folders${data?.file.folder_id ? `?folder=${data.file.folder_id}` : ''}`}>Back to files</Link></header>
    <p>Versions keep the file’s current name, location and permissions. Restoring changes its content. Existing external links revoke when content changes. Files remain unscanned.</p>
    {query.isPending && <p>Loading versions…</p>}
    {query.error && <p role="alert">{query.error instanceof Error ? query.error.message : 'Unable to load versions'}</p>}
    <button className="secondary-button" disabled={busy || query.isFetching} onClick={() => void query.refetch()}>Refresh versions</button>
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    {data && <>
      <section className="content-card p-5"><h2 className="section-title">Current: version {data.file.current_version ?? 1}</h2><p>Retained bytes: {data.retained_bytes.toLocaleString()} · Pending declared bytes: {data.pending_bytes.toLocaleString()}</p><p>All retained content counts toward storage accounting, including older versions. Versions stay until the entire file is permanently deleted.</p></section>
      {data.file.can_write && <form className="content-card p-5 space-y-3" onSubmit={event => { event.preventDefault(); void upload(); }}><h2 className="section-title">Upload a new version</h2><p>Replacement upload limit: {config.data ? `${config.data.max_bytes.toLocaleString()} bytes` : 'Loading…'}. Retry with the same selected file after a lost response. Refresh after a version conflict, then select the file again.</p><label className="block">Replacement file<input aria-label="Replacement file" type="file" disabled={busy} onChange={event => { request.current = crypto.randomUUID(); setSelected(event.target.files?.[0] ?? null); setError(''); }} /></label><button className="primary-button" disabled={busy || !selected || !config.data?.enabled}>Upload new version</button>{config.error && <p role="alert">Upload configuration unavailable</p>}</form>}
      <ul className="content-card divide-y">{data.items.map(version => <li className="p-5 space-y-2" key={version.id}><h2 className="font-semibold">Version {version.number}{version.is_current ? ' · Current' : ''}</h2><p>{version.status === 'uploaded' ? `${version.size_bytes?.toLocaleString()} verified bytes` : `${version.declared_size_bytes.toLocaleString()} declared bytes · Pending`}</p><p>Created {new Date(version.created_at).toLocaleString()} · Uploader {version.created_by}</p><div className="flex flex-wrap gap-3">{version.status === 'uploaded' && <button className="secondary-button" disabled={busy} onClick={() => void download(version.id)}>Download version {version.number}</button>}{data.file.can_write && version.status === 'uploaded' && !version.is_current && <button className="secondary-button" disabled={busy} onClick={() => setRestore({ id: version.id, number: version.number })}>Restore version {version.number}</button>}{version.status === 'pending' && <p>{version.can_complete ? 'Upload may be retried with the original file.' : 'Expired or superseded; retained for automatic cleanup.'}</p>}</div></li>)}</ul>
      {restore && <section className="content-card p-5 space-y-3" aria-label="Restore confirmation"><h2>Make version {restore.number} current?</h2><p>All versions remain available. Existing external links will be revoked.</p><button className="primary-button" disabled={busy} onClick={() => void action(async () => { await api.restoreVersion(fileId, restore.id, data.file.version_generation ?? 1, controller.current.signal); if (controller.current.signal.aborted) return; setRestore(null); await invalidate(); setMessage('Version restored.'); })}>Confirm restore</button><button className="secondary-button" disabled={busy} onClick={() => setRestore(null)}>Cancel</button></section>}
      <div className="flex gap-3"><button className="secondary-button" disabled={busy || !offset || query.isFetching} onClick={() => setOffset(Math.max(0, offset - 25))}>Previous versions</button><button className="secondary-button" disabled={busy || !data.has_more || query.isFetching || offset + 25 > 10000} onClick={() => setOffset(offset + 25)}>Next versions</button></div>
    </>}
  </main>;
}
