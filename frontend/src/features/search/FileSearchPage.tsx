import { useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../../auth/AuthContext';
import { Icon } from '../../components/ui/Icon';
import { DownloadButton } from '../folders/DownloadButton';
import { api } from '../../services/api';
import type { FileSearchQuery } from '../../types';

const defaults = { q: '', status: '', upload_method: '', declared_content_type: '', min_bytes: '', max_bytes: '',
  mine: false, scope: 'workspace', sort: 'name', direction: 'asc', limit: '25' };

export function FileSearchPage() {
  const { user } = useAuth();
  const [params] = useSearchParams();
  const folderId = params.get('folder');
  return <SearchWorkspace key={`${user?.tenant?.id}:${user?.id}:${folderId}`} folderId={folderId} />;
}

function SearchWorkspace({ folderId }: { folderId: string | null }) {
  const { user } = useAuth();
  const [draft, setDraft] = useState({ ...defaults, scope: folderId ? 'folder' : 'workspace' });
  const [filters, setFilters] = useState<FileSearchQuery>({ scope: folderId ? 'folder' : 'workspace', folder_id: folderId ?? undefined, sort: 'name', direction: 'asc' });
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState('');
  const pageSize = filters.limit ?? 25;
  const query = useQuery({ queryKey: ['file-search', user?.tenant?.id, user?.id, filters, offset],
    queryFn: ({ signal }) => api.searchFiles({ ...filters, offset, limit: pageSize }, signal) });
  function submit(event: FormEvent) {
    event.preventDefault(); setError('');
    const minimum = draft.min_bytes === '' ? undefined : Number(draft.min_bytes);
    const maximum = draft.max_bytes === '' ? undefined : Number(draft.max_bytes);
    if ([minimum, maximum].some(value => value !== undefined && (!Number.isSafeInteger(value) || value < 0)) ||
      (minimum !== undefined && maximum !== undefined && minimum > maximum)) {
      setError('Enter whole-byte sizes with minimum no greater than maximum.'); return;
    }
    setOffset(0);
    setFilters({ q: draft.q.trim(), scope: draft.scope as FileSearchQuery['scope'], folder_id: draft.scope === 'folder' ? folderId ?? undefined : undefined,
      status: draft.status ? draft.status as FileSearchQuery['status'] : undefined,
      upload_method: draft.upload_method ? draft.upload_method as FileSearchQuery['upload_method'] : undefined,
      declared_content_type: draft.declared_content_type.trim() || undefined, created_by: draft.mine ? user?.id : undefined,
      min_bytes: minimum, max_bytes: maximum, sort: draft.sort as FileSearchQuery['sort'], direction: draft.direction as FileSearchQuery['direction'], limit: Number(draft.limit) });
  }
  function clear() {
    setDraft(defaults); setFilters({ scope: 'workspace', sort: 'name', direction: 'asc' }); setOffset(0); setError('');
  }
  return <main className="file-search-page space-y-6">
    <header className="page-heading"><div><p className="eyebrow">WORKSPACE LIBRARY</p><h1>Find your files.</h1><p>Search filenames across your workspace. Files remain unscanned.</p></div><Link to="/app/folders" className="secondary-button">Files & folders</Link></header>
    <form onSubmit={submit} className="content-card p-5 space-y-4" aria-label="File search">
      <label className="block">Filename<input type="search" maxLength={128} value={draft.q} onChange={event => setDraft({ ...draft, q: event.target.value })} placeholder="Search by part of a filename" className="block w-full" /></label>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <label>Search scope<select className="block w-full" value={draft.scope} onChange={event => setDraft({ ...draft, scope: event.target.value })}><option value="workspace">Whole workspace</option><option value="root">Root files</option>{folderId && <option value="folder">Selected folder</option>}</select></label>
        <label>Upload status<select className="block w-full" value={draft.status} onChange={event => setDraft({ ...draft, status: event.target.value })}><option value="">All statuses</option><option value="uploaded">Uploaded</option><option value="pending">Pending</option></select></label>
        <label>Transfer method<select className="block w-full" value={draft.upload_method} onChange={event => setDraft({ ...draft, upload_method: event.target.value })}><option value="">All methods</option><option value="basic">Basic</option><option value="multipart">Multipart</option></select></label>
        <label>Declared type<input className="block w-full" value={draft.declared_content_type} maxLength={255} placeholder="e.g. application/pdf" onChange={event => setDraft({ ...draft, declared_content_type: event.target.value })} /></label>
        <label>Minimum bytes<input className="block w-full" type="number" min="0" max={Number.MAX_SAFE_INTEGER} step="1" value={draft.min_bytes} onChange={event => setDraft({ ...draft, min_bytes: event.target.value })} /></label>
        <label>Maximum bytes<input className="block w-full" type="number" min="0" max={Number.MAX_SAFE_INTEGER} step="1" value={draft.max_bytes} onChange={event => setDraft({ ...draft, max_bytes: event.target.value })} /></label>
        <label>Sort by<select className="block w-full" value={draft.sort} onChange={event => setDraft({ ...draft, sort: event.target.value })}><option value="name">Filename</option><option value="size">Size</option><option value="created_at">Created date</option><option value="updated_at">Updated date</option></select></label>
        <label>Sort direction<select className="block w-full" value={draft.direction} onChange={event => setDraft({ ...draft, direction: event.target.value })}><option value="asc">Ascending</option><option value="desc">Descending</option></select></label>
        <label>Results per page<select className="block w-full" value={draft.limit} onChange={event => setDraft({ ...draft, limit: event.target.value })}><option value="5">5</option><option value="25">25</option><option value="50">50</option></select></label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={draft.mine} onChange={event => setDraft({ ...draft, mine: event.target.checked })} />Created by me</label>
      </div>
      <p className="text-sm">Size uses the declaration for pending uploads. Declared types are not verified content types.</p>
      <div className="flex flex-wrap gap-3"><button className="primary-button" disabled={query.isFetching}>Search files</button><button type="button" className="secondary-button" onClick={clear}>Clear filters</button></div>
      {error && <p role="alert">{error}</p>}
    </form>
    <section aria-label="Search results" className="space-y-3">
      <h2 className="section-title">Results</h2>
      {query.isPending && <p role="status">Searching files…</p>}
      {query.error && <><p role="alert">{query.error instanceof Error ? query.error.message : 'Search unavailable'}</p><button className="secondary-button" onClick={() => void query.refetch()}>Retry search</button></>}
      {query.data && <p role="status">{query.data.items.length ? `Showing ${offset + 1}–${offset + query.data.items.length}` : 'No matching files.'}</p>}
      <ul className="file-list content-card divide-y">{query.data?.items.map(file => <li key={file.id} className="file-row p-4">
        <p className="file-name"><span className="file-icon"><Icon name="file" /></span><strong>{file.name}</strong><span className={`status-badge ${file.status}`}>{file.multipart_state === 'aborted' ? 'Cancelled' : file.status === 'uploaded' ? 'Uploaded' : 'Pending'}</span></p>
        <p>{file.status === 'uploaded' ? 'Verified' : 'Declared'} size: {(file.size_bytes ?? file.declared_size_bytes).toLocaleString()} bytes · {file.declared_content_type ?? 'Type unspecified'}</p>
        <p>Location: {file.folder_id ? file.folder_name ?? 'Folder' : 'Root'}</p>
        <div className="flex flex-wrap gap-3"><Link className="secondary-button" aria-label={`Open folder for ${file.name}`} to={`/app/folders${file.folder_id ? `?folder=${encodeURIComponent(file.folder_id)}` : ''}`}>Open folder</Link>{file.status === 'uploaded' && <DownloadButton id={file.id} name={file.name} />}</div>
      </li>)}</ul>
      {query.data?.items.length === 0 && <div className="empty-state"><Icon name="search" /><strong>No matching files.</strong><p>Try another filename or clear the filters.</p></div>}
      <div className="flex gap-3"><button className="secondary-button" disabled={!offset || query.isFetching} onClick={() => setOffset(Math.max(0, offset - pageSize))}>Previous results</button><button className="secondary-button" disabled={!query.data?.has_more || query.isFetching || offset + pageSize > 10000} onClick={() => setOffset(offset + pageSize)}>Next results</button></div>
      {offset + pageSize > 10000 && query.data?.has_more && <p>Refine the filters to see more relevant results.</p>}
    </section>
  </main>;
}
