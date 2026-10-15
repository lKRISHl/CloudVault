import { Icon } from '../../components/ui/Icon';
import { Link } from 'react-router-dom';
import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthContext';
import { api } from '../../services/api';
import { UploadForm } from './UploadForm';
import { DownloadButton } from './DownloadButton';
import { RenameFile } from './RenameFile';
import { TrashButton } from '../trash/TrashButton';
import { FileRecoveryActions } from './FileRecoveryActions';

export function FileList({ folderId, writable = false }: { folderId: string | null; writable?: boolean }) {
  const { user } = useAuth();
  const cache = useQueryClient();
  const [cancelId, setCancelId] = useState<string | null>(null);
  const [cancelError, setCancelError] = useState('');
  async function cancel(id: string) {
    setCancelId(id); setCancelError('');
    try { await api.abortMultipart(id); await cache.invalidateQueries({ queryKey: ['files', user?.tenant?.id, user?.id] }); }
    catch (failure) { setCancelError(failure instanceof Error ? failure.message : 'Cancellation failed'); }
    finally { setCancelId(null); }
  }
  const [offset, setOffset] = useState(0);
  const [retryId, setRetryId] = useState<string | null>(null);
  const query = useQuery({ queryKey: ['files', user?.tenant?.id, user?.id, folderId, offset],
    queryFn: () => api.files(folderId, offset) });
  return <section aria-label="Files" className="file-section space-y-3">
    <h2 className="section-title">Files <span>Workspace library</span></h2>
    <p>Resource and containing folder permissions govern access. Files remain unscanned; open only content you trust.</p>
    {writable && <UploadForm key={retryId ?? 'new-upload'} folderId={folderId} retryId={retryId}
      multipartRetry={query.data?.items.some(file => file.id === retryId && file.upload_method === 'multipart') ?? false}
      finished={() => setRetryId(null)} />}
    {cancelError && <p role="alert">{cancelError}</p>}
    {query.isPending && <p>Loading file metadata…</p>}
    {query.error && <>
      <p role="alert">{query.error instanceof Error ? query.error.message : 'Unable to load files'}</p>
      <button className="border rounded px-3 py-2" disabled={query.isFetching} onClick={() => void query.refetch()}>Retry files</button>
    </>}
    <ul className="file-list content-card divide-y">{query.data?.items.map((file) => <li key={file.id} className="file-row p-4">
      <p className="file-name font-medium"><span className="file-icon"><Icon name="file" /></span><span>{file.name}</span><span className={`status-badge ${file.status}`}>{file.status === 'uploaded' ? 'Uploaded' : file.multipart_state === 'aborted' ? 'Cancelled' : 'Pending'}</span></p>
      <p>{file.status === 'uploaded' ? `Uploaded · Verified size: ${file.size_bytes?.toLocaleString()} bytes · Unscanned` : `Pending upload · Declared size: ${file.declared_size_bytes.toLocaleString()} bytes`}</p>
      {file.upload_method === 'multipart' && <p>{file.multipart_state === 'aborted' ? 'Multipart upload cancelled. The name stays reserved until cleanup.' : 'Chunked upload'}</p>}
      <p>Declared type: {file.declared_content_type ?? 'Type unspecified'}</p>
      <p>{file.can_write ? 'Creator or manager access' : 'Read only'}</p>
      {file.status === 'uploaded' && <DownloadButton id={file.id} name={file.name} />}
      {file.status === 'uploaded' && <Link className="secondary-button ml-3" to={`/app/files/${file.id}/versions`} aria-label={`Versions of ${file.name}`}>Versions</Link>}
      {file.status === 'uploaded' && file.can_manage && <Link className="secondary-button ml-3" to={`/app/files/${file.id}/shares`} aria-label={`Share ${file.name}`}>Share</Link>}
      {file.can_manage && <Link className="secondary-button ml-3" to={`/app/permissions/files/${file.id}`} aria-label={`Permissions for ${file.name}`}>Permissions</Link>}
      {file.status === 'uploaded' && file.can_write && <RenameFile id={file.id} name={file.name} />}
      {file.status === 'uploaded' && file.can_manage && <TrashButton kind="files" id={file.id} name={file.name} />}
      {file.can_manage && (file.status === 'uploaded' || file.legacy_metadata) && <FileRecoveryActions file={file} />}
      {file.upload_cancelled_at && <p>Upload cancelled. Outstanding transfers are cleaned after their original authorization deadline.</p>}
      {writable && file.status === 'pending' && !file.legacy_metadata && !file.upload_cancelled_at && file.upload_method !== 'multipart' && file.created_by === user?.id && <button className="border rounded px-3 py-2" onClick={() => setRetryId(file.id)}>Retry upload {file.name}</button>}
      {writable && file.status === 'pending' && file.upload_method === 'multipart' && file.multipart_state === 'active' && file.created_by === user?.id && <button className="border rounded px-3 py-2" disabled={cancelId !== null} onClick={() => void cancel(file.id)}>Cancel multipart upload {file.name}</button>}
      {writable && file.status === 'pending' && file.upload_method === 'multipart' && file.multipart_state === 'active' && file.created_by === user?.id && <button className="border rounded px-3 py-2" onClick={() => setRetryId(file.id)}>Resume upload {file.name}</button>}
    </li>)}</ul>
    {query.data?.items.length === 0 && <div className="empty-state"><Icon name="file" /><strong>No file metadata here.</strong><p>Your uploaded files will appear here. Choose a file above to get started.</p></div>}
    <button className="border rounded px-3 py-2 disabled:opacity-50" disabled={!offset || query.isFetching} onClick={() => setOffset(Math.max(0, offset - 25))}>Previous files</button>
    <button className="border rounded px-3 py-2 disabled:opacity-50" disabled={!query.data?.has_more || query.isFetching} onClick={() => setOffset(offset + 25)}>Next files</button>
  </section>;
}
