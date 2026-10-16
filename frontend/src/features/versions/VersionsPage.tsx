import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { api } from '../../services/api';
import type { FileVersion } from '../../types';
import { forgetVersionManifest, loadVersionManifest, transferVersion } from './versionTransfers';
import { ScanStatus } from '../folders/ScanStatus';

export function VersionsPage() {
  const { fileId = '' } = useParams(); const { user } = useAuth();
  return <Versions key={`${user?.tenant?.id}:${user?.id}:${fileId}`} fileId={fileId} />;
}

function Versions({ fileId }: { fileId: string }) {
  const { user } = useAuth(); const cache = useQueryClient();
  const key = `cloudvault.version.${user?.tenant?.id}.${user?.id}.${fileId}`;
  const [offset, setOffset] = useState(0); const [busy, setBusy] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState(''); const [message, setMessage] = useState('');
  const [selected, setSelected] = useState<File | null>(null);
  const [saved, setSaved] = useState(() => loadVersionManifest(key));
  const [resume, setResume] = useState<FileVersion | null>(null);
  const [restore, setRestore] = useState<{ id: string; number: number } | null>(null);
  const [prune, setPrune] = useState<{ id: string; number: number } | null>(null);
  const [confirmation, setConfirmation] = useState('');
  const [keep, setKeep] = useState(''); const [policyConfirmation, setPolicyConfirmation] = useState('');
  const controller = useRef(new AbortController()); const transfer = useRef<AbortController | null>(null);
  const cancelRequested = useRef(false); const input = useRef<HTMLInputElement>(null);
  useEffect(() => { controller.current = new AbortController(); return () => { controller.current.abort(); transfer.current?.abort(); }; }, []);
  const query = useQuery({ queryKey: ['versions', user?.tenant?.id, user?.id, fileId, offset], queryFn: ({ signal }) => api.versions(fileId, offset, signal), refetchInterval: query => query.state.data?.items.some(version => version.status === 'uploaded' && ['pending', 'scanning'].includes(version.scan_status ?? '')) ? 2000 : false });
  const config = useQuery({ queryKey: ['version-configuration', user?.tenant?.id, user?.id], queryFn: () => api.uploadConfiguration() });
  const data = query.data; const working = busy || cancelling;
  async function invalidate() {
    await cache.invalidateQueries({ predicate: entry => ['versions', 'files', 'file-search', 'shares'].includes(String(entry.queryKey[0])) });
  }
  async function action(operation: () => Promise<void>) {
    setBusy(true); setError(''); setMessage('');
    try { await operation(); }
    catch (failure) { if (!controller.current.signal.aborted) setError(failure instanceof Error ? failure.message : 'Version operation failed'); }
    finally { if (!controller.current.signal.aborted) setBusy(false); }
  }
  function clearLocal() { forgetVersionManifest(key); setSaved(null); setResume(null); setSelected(null); if (input.current) input.current.value = ''; }
  async function upload() {
    if (!selected || !data || !config.data) return;
    setBusy(true); setError(''); setMessage(''); cancelRequested.current = false;
    transfer.current = new AbortController();
    try {
      await transferVersion({ id: fileId, file: selected, key, generation: data.file.version_generation ?? 1,
        config: config.data, signal: transfer.current.signal, resume,
        progress: value => { if (!controller.current.signal.aborted) setMessage(value); },
        started: value => { if (!controller.current.signal.aborted) setSaved({ ...value }); } });
      if (!controller.current.signal.aborted) { clearLocal(); setMessage('Version uploaded and verified.'); }
    } catch (failure) {
      if (!controller.current.signal.aborted && !cancelRequested.current) {
        if (transfer.current.signal.aborted) setMessage('Upload paused. Reselect the original file to resume before its deadline.');
        else setError(failure instanceof Error ? failure.message : 'Upload failed');
      }
    } finally {
      if (!controller.current.signal.aborted) { setBusy(false); await invalidate(); }
    }
  }
  async function cancel(id: string) {
    setCancelling(true); setError(''); cancelRequested.current = true; transfer.current?.abort();
    try {
      const result = await api.cancelVersion(fileId, id, controller.current.signal);
      if (controller.current.signal.aborted) return;
      if (saved?.versionId === id || resume?.id === id) clearLocal();
      await invalidate(); setMessage(result.detail);
    } catch (failure) { if (!controller.current.signal.aborted) setError(failure instanceof Error ? failure.message : 'Cancellation failed'); }
    finally { if (!controller.current.signal.aborted) setCancelling(false); }
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
    <p>Versions keep the file’s current name, location and permissions. Content changes revoke external links. Each version must pass scanning before downloads, previews or sharing. Queued history deletion is irreversible and waits for safe storage cleanup.</p>
    {query.isPending && <p>Loading versions…</p>}
    {query.error && <p role="alert">{query.error instanceof Error ? query.error.message : 'Unable to load versions'}</p>}
    <button className="secondary-button" disabled={working || query.isFetching} onClick={() => void query.refetch()}>Refresh versions</button>
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    {data && <>
      <section className="content-card p-5"><h2 className="section-title">Current: version {data.file.current_version ?? 1}</h2><p>Retained bytes: {data.retained_bytes.toLocaleString()} · Pending declared bytes: {data.pending_bytes.toLocaleString()}</p><p>Every retained version stays counted until confirmed cleanup. Current content is protected from pruning.</p></section>
      {data.file.can_write && <form className="content-card p-5 space-y-3" onSubmit={event => { event.preventDefault(); void upload(); }}>
        <h2 className="section-title">Upload a new version</h2>
        <p>Large replacements use chunked uploads; empty files use basic upload. Multipart limit: {config.data?.multipart_max_bytes?.toLocaleString() ?? 'Loading…'} bytes. Reselect the original file to resume within its original deadline.</p>
        {(saved || resume) && <p>Resume record: {resume ? `version ${resume.number}` : saved?.name}. The server rechecks the original content and permissions.</p>}
        <label className="block">Replacement file<input ref={input} aria-label="Replacement file" type="file" disabled={working} onChange={event => { setSelected(event.target.files?.[0] ?? null); setError(''); }} /></label>
        <div className="flex flex-wrap gap-3"><button className="primary-button" disabled={working || !selected || !config.data?.enabled}>Upload new version</button>
          {busy && <button type="button" className="secondary-button" onClick={() => transfer.current?.abort()}>Pause upload</button>}
          {saved?.versionId && <button type="button" className="secondary-button" disabled={cancelling} onClick={() => void cancel(saved.versionId!)}>Cancel active upload</button>}
          {!working && (saved || resume) && <button type="button" className="secondary-button" onClick={() => { clearLocal(); setMessage('Local resume record forgotten. Any server candidate remains until cancellation or cleanup; use its history controls.'); }}>Forget local resume record</button>}
        </div>{config.error && <p role="alert">Upload configuration unavailable</p>}
      </form>}
      {data.file.can_manage && <form className="content-card p-5 space-y-3" onSubmit={event => { event.preventDefault(); void action(async () => {
        const value = keep.trim() ? Number(keep) : null;
        if (value !== null && (!Number.isInteger(value) || value < 1 || value > 1000)) throw new Error('Keep between 1 and 1000 newest versions, or leave blank.');
        await api.versionPolicy(fileId, value, controller.current.signal); if (controller.current.signal.aborted) return;
        setPolicyConfirmation(''); await invalidate(); setMessage('Retention policy saved. Already queued deletions cannot be cancelled.');
      }); }}><h2 className="section-title">History retention</h2><p>Current policy: {data.file.version_keep_last ? `keep newest ${data.file.version_keep_last} plus current if older` : 'keep all history'}. Applying a smaller policy queues older history for deletion. Disabling the policy does not undo queued deletions.</p><label className="block">Keep newest versions (blank keeps all)<input aria-label="Keep newest versions" type="number" min="1" max="1000" value={keep} disabled={working} onChange={event => setKeep(event.target.value)} /></label><label className="block">Type PRUNE to apply retention<input aria-label="Type PRUNE to apply retention" value={policyConfirmation} disabled={working} onChange={event => setPolicyConfirmation(event.target.value)} /></label><button className="secondary-button" disabled={working || policyConfirmation !== 'PRUNE'}>Apply retention policy</button></form>}
      <ul className="content-card divide-y">{data.items.map(version => <li className="p-5 space-y-2" key={version.id}>
        <h2 className="font-semibold">Version {version.number}{version.is_current ? ' · Current' : ''}</h2>
        {version.status === 'uploaded' && <ScanStatus state={version.scan_status} />}
        {data.file.can_write && version.scan_status === 'error' && !version.prune_requested_at && <button className="secondary-button" disabled={working} onClick={() => void action(async () => { const result = await api.retryScan(fileId, version.id, controller.current.signal); await invalidate(); setMessage(result.detail); })}>Retry scan version {version.number}</button>}
        <p>{version.status === 'uploaded' ? `${version.size_bytes?.toLocaleString()} verified bytes` : `${version.declared_size_bytes.toLocaleString()} declared bytes · Pending`}{version.cancelled_at ? ' · Cancelled; cleanup pending' : ''}{version.prune_requested_at ? ' · Deletion queued' : ''}</p>
        <p className="break-words">Created {new Date(version.created_at).toLocaleString()} · Uploader {version.created_by}</p>
        <div className="flex flex-wrap gap-3">
          {version.status === 'uploaded' && !version.prune_requested_at && <button className="secondary-button" disabled={working} onClick={() => void download(version.id)}>Download version {version.number}</button>}
          {version.status === 'uploaded' && !version.prune_requested_at && <Link className="secondary-button" to={`/app/files/${fileId}/preview?version=${version.id}`}>Preview version {version.number}</Link>}
          {data.file.can_write && version.status === 'uploaded' && !version.is_current && !version.prune_requested_at && <button className="secondary-button" disabled={working} onClick={() => setRestore({ id: version.id, number: version.number })}>Restore version {version.number}</button>}
          {data.file.can_manage && version.status === 'uploaded' && !version.is_current && !version.prune_requested_at && <button className="secondary-button" disabled={working} onClick={() => { setPrune({ id: version.id, number: version.number }); setConfirmation(''); }}>Delete version {version.number}</button>}
          {data.file.can_write && version.status === 'pending' && version.created_by === user?.id && !version.cancelled_at && <>
            {version.can_complete && <button className="secondary-button" disabled={working} onClick={() => { forgetVersionManifest(key); setSaved(null); setResume(version); setSelected(null); if (input.current) input.current.value = ''; setMessage(`Reselect the original file for version ${version.number}, then upload to resume.`); }}>Resume version {version.number}</button>}
            <button className="secondary-button" disabled={working} onClick={() => void cancel(version.id)}>Cancel version {version.number}</button>
          </>}
          {version.status === 'pending' && !version.can_complete && !version.cancelled_at && <p>Expired or superseded; cancel or await cleanup.</p>}
        </div>
      </li>)}</ul>
      {restore && <section className="content-card p-5 space-y-3" aria-label="Restore confirmation"><h2>Make version {restore.number} current?</h2><p>Current content is protected. A retention policy may queue older non-current history; external links revoke.</p><button className="primary-button" disabled={working} onClick={() => void action(async () => { await api.restoreVersion(fileId, restore.id, data.file.version_generation ?? 1, controller.current.signal); if (controller.current.signal.aborted) return; setRestore(null); await invalidate(); setMessage('Version restored.'); })}>Confirm restore</button><button className="secondary-button" disabled={working} onClick={() => setRestore(null)}>Cancel</button></section>}
      {prune && <section className="content-card p-5 space-y-3" aria-label="Delete version confirmation"><h2>Delete version {prune.number} permanently?</h2><p>This queues irreversible deletion of this historical content. Existing download authorizations and upload deadlines are respected; retained bytes stay counted until cleanup confirms removal.</p><label className="block">Type DELETE to remove history<input aria-label="Type DELETE to remove history" value={confirmation} onChange={event => setConfirmation(event.target.value)} disabled={working} /></label><button className="primary-button" disabled={working || confirmation !== 'DELETE'} onClick={() => void action(async () => { const result = await api.pruneVersion(fileId, prune.id, controller.current.signal); if (controller.current.signal.aborted) return; setPrune(null); setConfirmation(''); await invalidate(); setMessage(result.detail); })}>Confirm history deletion</button><button className="secondary-button" disabled={working} onClick={() => setPrune(null)}>Cancel deletion</button></section>}
      <div className="flex gap-3"><button className="secondary-button" disabled={working || !offset || query.isFetching} onClick={() => setOffset(Math.max(0, offset - 25))}>Previous versions</button><button className="secondary-button" disabled={working || !data.has_more || query.isFetching || offset + 25 > 10000} onClick={() => setOffset(offset + 25)}>Next versions</button></div>
    </>}
  </main>;
}
