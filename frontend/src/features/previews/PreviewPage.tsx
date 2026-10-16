import { useEffect, useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { api } from '../../services/api';
import type { PreviewResult } from '../../types';

export function PreviewPage() {
  const { fileId = '' } = useParams(); const [parameters] = useSearchParams();
  const { user } = useAuth(); const version = parameters.get('version');
  return <Preview key={`${user?.id}:${user?.tenant?.id}:${fileId}:${version}`} id={fileId} version={version} />;
}

function Preview({ id, version }: { id: string; version: string | null }) {
  const [page, setPage] = useState(0); const [reload, setReload] = useState(0);
  const [result, setResult] = useState<PreviewResult | null>(null);
  const [image, setImage] = useState(''); const [error, setError] = useState('');
  const [busy, setBusy] = useState(true); const current = useRef(0);
  const pending = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController(); const epoch = ++current.current; let url = '';
    pending.current = controller;
    setBusy(true); setError(''); setResult(null); setImage('');
    void api.preview(id, version, page, controller.signal).then(data => {
      if (controller.signal.aborted || current.current !== epoch) return;
      if (data.image_base64 && (data.kind === 'image' || data.kind === 'pdf' || data.kind === 'video')) {
        const raw = atob(data.image_base64);
        url = URL.createObjectURL(new Blob([Uint8Array.from(raw, char => char.charCodeAt(0))], { type: 'image/png' }));
        setImage(url);
      }
      setResult(data);
    }).catch(failure => {
      if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : 'Preview unavailable');
    }).finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => { controller.abort(); if (url) URL.revokeObjectURL(url); };
  }, [id, version, page, reload]);
  return <main className="space-y-5">
    <header><p className="eyebrow">Read your content</p><h1 className="page-title">File preview</h1><p className="break-words">{result?.name}</p></header>
    <div className="flex flex-wrap gap-3"><Link className="secondary-button" to="/app/folders">Back to files</Link><Link className="secondary-button" to={`/app/files/${id}/versions`}>Versions and downloads</Link></div>
    <p>Content is unscanned. Images, PDF pages and video posters are rendered as static PNGs; UTF-8 content is displayed as text. Video posters support selected MP4/WebM videos up to two minutes. Only supported content up to 10 MiB can be previewed.</p>
    <button className="secondary-button" disabled={busy} onClick={() => { setPage(0); setReload(reload + 1); }}>Refresh preview</button>
    {busy && <button className="secondary-button" onClick={() => { pending.current?.abort(); setBusy(false); setError('Preview cancelled. Refresh to try again.'); }}>Cancel preview</button>}
    {busy && <p role="status">Preparing bounded preview…</p>}
    {error && <p role="alert">{error}</p>}
    {result && <section className="content-card p-4 space-y-3">
      <p>Version {result.version_number} · {result.detected_type ?? 'Unsupported type'} · Unscanned</p>
      {result.kind === 'video' && <p>Static video poster. Use Versions and downloads for playback of the original.</p>}
      {result.kind === 'unsupported' && <p role="status">{result.reason} Use Versions and downloads for the original.</p>}
      {result.kind === 'text' && <pre aria-label="Text preview" className="whitespace-pre-wrap break-words overflow-auto max-h-[70vh]">{result.text}</pre>}
      {image && <img src={image} alt={`Static preview of ${result.name}, page ${result.page + 1}`} className="max-w-full max-h-[75vh] object-contain" referrerPolicy="no-referrer" />}
      {result.truncated && <p>Preview is truncated to its safe display limit.</p>}
      {result.kind === 'pdf' && <div className="flex flex-wrap gap-3"><p>Page {result.page + 1} of {result.pages}</p><button className="secondary-button" disabled={busy || page === 0} onClick={() => setPage(page - 1)}>Previous PDF page</button><button className="secondary-button" disabled={busy || page + 1 >= result.pages} onClick={() => setPage(page + 1)}>Next PDF page</button></div>}
    </section>}
  </main>;
}
