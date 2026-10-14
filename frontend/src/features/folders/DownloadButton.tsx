import { useEffect, useRef, useState } from 'react';
import { downloadBrowserFile } from '../../services/api';

export function DownloadButton({ id, name }: { id: string; name: string }) {
  const controller = useRef<AbortController | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => () => controller.current?.abort(), []);
  async function download() {
    setBusy(true); setError('');
    const request = new AbortController(); controller.current = request;
    try { await downloadBrowserFile(id, request.signal); }
    catch (failure) { if (!request.signal.aborted) setError(failure instanceof Error ? failure.message : 'Unable to authorize download'); }
    finally { if (!request.signal.aborted) setBusy(false); }
  }
  return <div className="mt-3">
    <button className="border rounded px-3 py-2" aria-label={`Download ${name}`} disabled={busy} onClick={() => void download()}>{busy ? 'Preparing…' : 'Download'}</button>
    {error && <p role="alert">{error} Try downloading again.</p>}
  </div>;
}
