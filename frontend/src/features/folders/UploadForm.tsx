import { Icon } from '../../components/ui/Icon';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthContext';
import { api, uploadBrowserFile, uploadMultipartFile } from '../../services/api';

export function UploadForm({ folderId, retryId, finished, multipartRetry = false }: {
  folderId: string | null; retryId: string | null; finished: () => void; multipartRetry?: boolean;
}) {
  const { user } = useAuth();
  const cache = useQueryClient();
  const config = useQuery({ queryKey: ['upload-config', user?.tenant?.id, user?.id], queryFn: api.uploadConfiguration });
  const saved = useQuery({ queryKey: ['upload-progress', user?.tenant?.id, user?.id, retryId],
    queryFn: () => api.multipartProgress(retryId!), enabled: multipartRetry && !!retryId, retry: false });
  const [file, setFile] = useState<File | null>(null);
  const [activeMultipartId, setActiveMultipartId] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const cancelRequested = useRef(false);
  const formRef = useRef<HTMLFormElement>(null);
  const [multipart, setMultipart] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const requestId = useRef(crypto.randomUUID());
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => {
    if (saved.data?.file.status === 'uploaded') {
      void cache.invalidateQueries({ queryKey: ['files', user?.tenant?.id, user?.id] });
      finished();
    }
  }, [saved.data?.file.status, cache, user?.tenant?.id, user?.id, finished]);
  async function cancelMultipart() {
    if (!activeMultipartId) return;
    cancelRequested.current = true; controller.current?.abort(); setCancelling(true); setError('');
    try {
      await api.abortMultipart(activeMultipartId);
      await cache.invalidateQueries({ queryKey: ['files', user?.tenant?.id, user?.id] });
      setActiveMultipartId(null); setFile(null); formRef.current?.reset(); requestId.current = crypto.randomUUID();
      setMessage('Multipart upload cancelled. Its name remains reserved until cleanup.');
    } catch (failure) { setMessage(''); setError(failure instanceof Error ? failure.message : 'Cancellation failed.'); }
    finally { setCancelling(false); }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    const form = event.currentTarget as HTMLFormElement;
    if (!file || !config.data?.enabled) return;
    setError(''); setMessage('');
    const useMultipart = multipartRetry || (!retryId && (multipart || file.size > config.data.max_bytes));
    const maximum = useMultipart ? config.data.multipart_max_bytes ?? 0 : config.data.max_bytes;
    if (file.size > maximum && !multipartRetry) { setError(`File exceeds the ${useMultipart ? 'multipart' : 'basic upload'} size limit.`); return; }
    cancelRequested.current = false; setBusy(true); controller.current = new AbortController();
    try {
      if (useMultipart) await uploadMultipartFile(file, folderId, requestId.current, config.data.multipart_part_size ?? 8 * 1024 * 1024, maximum, controller.current.signal, setMessage, setActiveMultipartId, multipartRetry ? retryId ?? undefined : undefined);
      else await uploadBrowserFile(file, folderId, requestId.current, retryId, controller.current.signal, setMessage);
      await cache.invalidateQueries({ queryKey: ['files', user?.tenant?.id, user?.id] });
      form.reset(); setFile(null); requestId.current = crypto.randomUUID();
      setActiveMultipartId(null); setMessage('File uploaded and verified.'); finished();
    } catch (failure) {
      await cache.invalidateQueries({ queryKey: ['files', user?.tenant?.id, user?.id] });
      if (multipartRetry) await cache.invalidateQueries({ queryKey: ['upload-progress', user?.tenant?.id, user?.id, retryId] });
      if (!cancelRequested.current) { setMessage(''); setError(failure instanceof Error ? failure.message : 'Upload failed.'); }
    } finally { setBusy(false); }
  }
  return <form ref={formRef} onSubmit={(event) => void submit(event)} className="upload-panel space-y-3">
    <div className="upload-heading"><span className="upload-icon"><Icon name="upload" /></span><div><h3>{retryId ? 'Resume your upload' : 'Bring your work here'}</h3><p>{retryId ? 'Choose the original file to retry this pending upload.' : 'Upload a file to this folder.'}</p></div></div>
    {config.data && <p>Maximum file size: {config.data.max_bytes.toLocaleString()} bytes. Uploads remain unscanned.</p>}
    {!!config.data?.multipart_max_bytes && !retryId && <><p>Multipart limit: {config.data.multipart_max_bytes.toLocaleString()} bytes. Larger files use chunked upload automatically.</p><label className="flex items-center gap-2"><input type="checkbox" checked={multipart} disabled={busy} onChange={event => setMultipart(event.target.checked)} />Use multipart upload</label></>}
    {config.data && !config.data.enabled && <p>Uploads are not configured.</p>}
    {saved.data && <><p role="status">Saved progress: {Math.floor(saved.data.confirmed_bytes / saved.data.file.declared_size_bytes * 100)}% · {saved.data.confirmed_bytes.toLocaleString()} of {saved.data.file.declared_size_bytes.toLocaleString()} bytes confirmed.</p>
      {!saved.data.can_resume && <p>Upload window ended. Finish verification if every part arrived, or start again after cleanup.</p>}
      {saved.data.file.status === 'pending' && saved.data.parts.every(part => part.confirmed) && <button type="button" className="border rounded px-3 py-2" onClick={() => {
        void api.completeMultipart(retryId!).then(async () => { await cache.invalidateQueries({ queryKey: ['files', user?.tenant?.id, user?.id] }); finished(); })
          .catch(failure => setError(failure instanceof Error ? failure.message : 'Verification failed'));
      }}>Verify completed upload</button>}</>}
    {saved.error && <><p role="alert">{saved.error instanceof Error ? saved.error.message : 'Progress unavailable'}</p><button type="button" onClick={() => void saved.refetch()}>Retry upload progress</button></>}
    {config.error && <p role="alert">Unable to load upload settings.</p>}
    {config.error && <button type="button" className="border rounded px-3 py-2" disabled={config.isFetching} onClick={() => void config.refetch()}>Retry upload settings</button>}
    <label className="block">File to upload<input className="block" type="file" disabled={busy || !config.data?.enabled}
      onChange={(event) => { setFile(event.target.files?.[0] ?? null); setActiveMultipartId(null); requestId.current = crypto.randomUUID(); setMessage(''); setError(''); }} /></label>
    <button className="primary-button" disabled={busy || cancelling || !file || !config.data?.enabled || (multipartRetry && (!saved.data?.can_resume || saved.isFetching))}>{busy ? 'Uploading…' : 'Upload file'}</button>
    {activeMultipartId && <button type="button" className="border rounded px-3 py-2" disabled={cancelling} onClick={() => void cancelMultipart()}>{cancelling ? 'Cancelling…' : 'Cancel multipart transfer'}</button>}
    {message && <p role="status">{message}</p>}
    {error && <p role="alert">{error} You can retry with the same file while its upload authorization is valid.</p>}
  </form>;
}
