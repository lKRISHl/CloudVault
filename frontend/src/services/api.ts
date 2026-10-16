import type { AccountSession, AcceptInvitationPayload, EmailDelivery, HealthResponse, Invitation, InvitationCreated, LoginPayload, Member, ReadinessResponse, RegisterPayload, Tenant, TokenResponse, User, Workspace, Folder, FolderPage, FilePage, FileMetadata, UploadTicket, DownloadTicket, MultipartTicket, MultipartStart, MultipartProgress, PartTicket } from '../types';
import type { FileSearchQuery, FileSearchPage } from '../types';
import type { ShareLink } from '../types';
import type { TrashEntry } from '../types';
import type { VersionPage, VersionStart, VersionTicket } from '../types';
import type { VersionMultipartTicket } from '../types';
import type { PreviewJob, PreviewResult } from '../types';

const API_BASE = import.meta.env.VITE_API_URL || '';
const API_V1 = `${API_BASE}/api/v1`;

let accessToken: string | null = null;
let refreshPromise: Promise<TokenResponse> | null = null;
let sessionEpoch = 0;
const sessionExpiredListeners = new Set<() => void>();

export function onSessionExpired(listener: () => void) {
  sessionExpiredListeners.add(listener);
  return () => { sessionExpiredListeners.delete(listener); };
}

export function setAccessToken(token: string | null) {
  sessionEpoch += 1;
  accessToken = token;
}

export function beginSessionChange() { sessionEpoch += 1; }
export function getSessionEpoch() { return sessionEpoch; }

export function getAccessToken() {
  return accessToken;
}

export class ApiRequestError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiRequestError';
    this.status = status;
  }
}

async function parseError(response: Response): Promise<string> {
  try {
    const errorData = await response.json();
    if (typeof errorData.detail === 'string') {
      return errorData.detail;
    }
  } catch {
    // Response body is not JSON
  }
  return `API error: ${response.status}`;
}

function refreshSession(): Promise<TokenResponse> {
  if (!refreshPromise) {
    const epoch = sessionEpoch;
    refreshPromise = fetchApi<TokenResponse>(`${API_V1}/auth/refresh`, {
      method: 'POST',
    }, false).then((session) => {
      if (epoch !== sessionEpoch) throw new ApiRequestError('Session changed; try again', 409);
      const workspace = (token: string) => {
        try { return JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))).tid; }
        catch { return undefined; }
      };
      if (accessToken && workspace(accessToken) !== workspace(session.access_token)) {
        throw new ApiRequestError('Workspace changed in another tab; reload to continue', 401);
      }
      accessToken = session.access_token;
      return session;
    }).finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

async function tryRefresh(): Promise<boolean> {
  try {
    await refreshSession();
    return true;
  } catch {
    return false;
  }
}

async function fetchApi<T>(url: string, options?: RequestInit, retry = true): Promise<T> {
  const epoch = sessionEpoch;
  const scoped = !['/account/verify', '/account/reset-password', '/account/recovery-request', '/health', '/health/ready'].some((path) => url.endsWith(path));
  const headers = new Headers(options?.headers);
  headers.set('Accept', 'application/json');
  if (options?.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`);
  }

  const response = await fetch(url, {
    ...options,
    headers,
    credentials: 'include',
  });
  if (scoped && epoch !== sessionEpoch) throw new ApiRequestError('Workspace or session changed; try again', 409);

  if (response.status === 401 && retry && !url.includes('/auth/refresh') && !url.includes('/auth/login')) {
    const refreshed = await tryRefresh();
    if (scoped && epoch !== sessionEpoch) throw new ApiRequestError('Workspace or session changed; try again', 409);
    if (refreshed) {
      return fetchApi<T>(url, options, false);
    }
  }

  if (response.status === 204) {
    return undefined as T;
  }

  if (!response.ok) {
    const sessionEndpoints = ['/auth/login', '/auth/register', '/auth/refresh', '/auth/logout',
      '/organizations/invitations/accept', '/account/recovery-request', '/account/verify', '/account/reset-password'];
    if (response.status === 401 && !sessionEndpoints.some((path) => url.endsWith(path))) {
      setAccessToken(null);
      sessionExpiredListeners.forEach((listener) => listener());
    }
    throw new ApiRequestError(await parseError(response), response.status);
  }

  const data = await response.json();
  if (scoped && epoch !== sessionEpoch) throw new ApiRequestError('Workspace or session changed; try again', 409);
  return data;
}

function previewDelay(signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const abort = () => { clearTimeout(timer); reject(new DOMException('Preview cancelled', 'AbortError')); };
    const timer = setTimeout(() => { signal?.removeEventListener('abort', abort); resolve(); }, 1500);
    if (signal?.aborted) abort(); else signal?.addEventListener('abort', abort, { once: true });
  });
}

async function queuedPreview(id: string, version_id: string | null, page: number, signal?: AbortSignal): Promise<PreviewResult> {
  const base = `${API_V1}/files/${id}/preview-jobs`;
  let job: PreviewJob | undefined;
  try {
    job = await fetchApi<PreviewJob>(base, { method: 'POST', body: JSON.stringify({ version_id, page, request_id: crypto.randomUUID() }), signal });
    for (let poll = 0; poll < 600; poll += 1) {
      if (job.state === 'ready' && job.preview) return job.preview;
      if (job.state === 'failed' || job.state === 'cancelled') throw new Error('Preview failed, expired or cancelled. Refresh to try again.');
      await previewDelay(signal);
      job = await fetchApi<PreviewJob>(`${base}/${job.id}`, { signal });
    }
    throw new Error('Preview wait expired. Refresh to try again.');
  } finally {
    if (signal?.aborted && job) void fetchApi(`${base}/${job.id}`, { method: 'DELETE' }).catch(() => {});
  }
}

export const api = {
  retryScan: (id: string, version: string, signal?: AbortSignal) => fetchApi<{ detail: string }>(`${API_V1}/files/${id}/versions/${version}/scan`, { method: 'POST', signal }),
  preview: (id: string, version_id: string | null, page = 0, signal?: AbortSignal) => queuedPreview(id, version_id, page, signal),
  startVersionMultipart: (id: string, payload: VersionStart & { part_size: number; checksums: string[] }, signal?: AbortSignal) => fetchApi<VersionMultipartTicket>(`${API_V1}/files/${id}/versions/multipart`, { method: 'POST', body: JSON.stringify(payload), signal }),
  versionProgress: (id: string, version: string, signal?: AbortSignal) => fetchApi<VersionMultipartTicket>(`${API_V1}/files/${id}/versions/${version}/progress`, { signal }),
  resumeVersion: (id: string, version: string, checksums: string[], signal?: AbortSignal) => fetchApi<VersionMultipartTicket>(`${API_V1}/files/${id}/versions/${version}/resume`, { method: 'POST', body: JSON.stringify({ checksums }), signal }),
  versionPartUrl: (id: string, version: string, number: number, signal?: AbortSignal) => fetchApi<PartTicket>(`${API_V1}/files/${id}/versions/${version}/parts/${number}/url`, { method: 'POST', signal }),
  confirmVersionPart: (id: string, version: string, number: number, signal?: AbortSignal) => fetchApi<PartTicket>(`${API_V1}/files/${id}/versions/${version}/parts/${number}/confirm`, { method: 'POST', signal }),
  retryVersion: (id: string, version: string, checksum: string, signal?: AbortSignal) => fetchApi<VersionTicket>(`${API_V1}/files/${id}/versions/${version}/upload-url`, { method: 'POST', body: JSON.stringify({ checksum_sha256: checksum }), signal }),
  cancelVersion: (id: string, version: string, signal?: AbortSignal) => fetchApi<{ detail: string }>(`${API_V1}/files/${id}/versions/${version}/cancel`, { method: 'POST', signal }),
  pruneVersion: (id: string, version: string, signal?: AbortSignal) => fetchApi<{ detail: string }>(`${API_V1}/files/${id}/versions/${version}/prune`, { method: 'POST', body: JSON.stringify({ confirmation: 'DELETE' }), signal }),
  versionPolicy: (id: string, keep: number | null, signal?: AbortSignal) => fetchApi<FileMetadata>(`${API_V1}/files/${id}/version-policy`, { method: 'PUT', body: JSON.stringify({ keep_last: keep, confirmation: 'PRUNE' }), signal }),
  versions: (id: string, offset = 0, signal?: AbortSignal) => fetchApi<VersionPage>(`${API_V1}/files/${id}/versions?offset=${offset}`, { signal }),
  startVersion: (id: string, payload: VersionStart, signal?: AbortSignal) => fetchApi<VersionTicket>(`${API_V1}/files/${id}/versions`, { method: 'POST', body: JSON.stringify(payload), signal }),
  completeVersion: (id: string, versionId: string, signal?: AbortSignal) => fetchApi<FileMetadata>(`${API_V1}/files/${id}/versions/${versionId}/complete`, { method: 'POST', signal }),
  restoreVersion: (id: string, versionId: string, generation: number, signal?: AbortSignal) => fetchApi<FileMetadata>(`${API_V1}/files/${id}/versions/${versionId}/restore`, { method: 'POST', body: JSON.stringify({ base_generation: generation }), signal }),
  versionDownload: (id: string, versionId: string, signal?: AbortSignal) => fetchApi<{ download_url: string; expires_at: string }>(`${API_V1}/files/${id}/versions/${versionId}/download-url`, { method: 'POST', signal }),
  trash: (offset = 0, signal?: AbortSignal) => fetchApi<{ items: TrashEntry[]; offset: number; has_more: boolean }>(`${API_V1}/trash?offset=${offset}`, { signal }),
  moveToTrash: (kind: 'files' | 'folders', id: string) => fetchApi<TrashEntry>(`${API_V1}/${kind}/${id}/trash`, { method: 'POST' }),
  restoreTrash: (id: string, options?: { use_original: boolean; destination_id: string | null; name?: string }) => fetchApi<void>(`${API_V1}/trash/${id}/restore`, { method: 'POST', ...(options ? { body: JSON.stringify(options) } : {}) }),
  cancelUploadsAndTrash: (id: string, confirmation: string) => fetchApi<TrashEntry>(`${API_V1}/folders/${id}/cancel-uploads-and-trash`, { method: 'POST', body: JSON.stringify({ confirmation }) }),
  moveFile: (id: string, folder_id: string | null, source_folder_id: string | null) => fetchApi<FileMetadata>(`${API_V1}/files/${id}/move`, { method: 'POST', body: JSON.stringify({ folder_id, source_folder_id }) }),
  discardMetadata: (id: string, confirmation: string) => fetchApi<void>(`${API_V1}/files/${id}/discard-metadata`, { method: 'POST', body: JSON.stringify({ confirmation }) }),
  purgeTrash: (id: string, confirmation: string) => fetchApi<{ detail: string }>(`${API_V1}/trash/${id}/purge`, { method: 'POST', body: JSON.stringify({ confirmation }) }),
  permissions: (kind: 'files' | 'folders', id: string, offset: number, signal?: AbortSignal) => fetchApi<{ name: string; visibility: 'workspace' | 'private'; items: { user_id: string; role: 'viewer' | 'editor' }[]; offset: number; has_more: boolean }>(`${API_V1}/${kind}/${id}/permissions?offset=${offset}`, { signal }),
  setVisibility: (kind: 'files' | 'folders', id: string, visibility: 'workspace' | 'private') => fetchApi<void>(`${API_V1}/${kind}/${id}/permissions`, { method: 'PATCH', body: JSON.stringify({ visibility }) }),
  setGrant: (kind: 'files' | 'folders', id: string, userId: string, role: 'viewer' | 'editor' | null) => fetchApi<void>(`${API_V1}/${kind}/${id}/permissions/${userId}`, { method: 'PUT', body: JSON.stringify({ role }) }),
  renameFile: (id: string, name: string) => fetchApi<FileMetadata>(`${API_V1}/files/${id}`, { method: 'PATCH', body: JSON.stringify({ name }) }),
  shares: (id: string, offset: number, signal?: AbortSignal) => fetchApi<{ file_name: string; items: ShareLink[]; offset: number; has_more: boolean }>(`${API_V1}/files/${id}/shares?offset=${offset}`, { signal }),
  createShare: (id: string, payload: { expires_in_hours: number; password: string | null; allow_download: boolean; max_downloads: number | null }) => fetchApi<ShareLink & { share_url: string }>(`${API_V1}/files/${id}/shares`, { method: 'POST', body: JSON.stringify(payload) }),
  revokeShare: (fileId: string, id: string) => fetchApi<void>(`${API_V1}/files/${fileId}/shares/${id}`, { method: 'DELETE' }),
  searchFiles: (filters: FileSearchQuery, signal?: AbortSignal) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => { if (value !== undefined && value !== '') params.set(key, String(value)); });
    return fetchApi<FileSearchPage>(`${API_V1}/files/search?${params}`, { signal });
  },
  uploadConfiguration: () => fetchApi<{ max_bytes: number; scan_max_bytes?: number; enabled: boolean; multipart_max_bytes?: number; multipart_part_size?: number }>(`${API_V1}/files/upload-configuration`),
  startUpload: (payload: { name: string; folder_id: string | null; declared_size_bytes: number; declared_content_type: string | null; checksum_sha256: string; request_id: string }) => fetchApi<UploadTicket>(`${API_V1}/files/uploads`, { method: 'POST', body: JSON.stringify(payload) }),
  retryUpload: (id: string, checksum_sha256: string) => fetchApi<UploadTicket>(`${API_V1}/files/${id}/upload-url`, { method: 'POST', body: JSON.stringify({ checksum_sha256 }) }),
  downloadTicket: (id: string, signal?: AbortSignal) => fetchApi<DownloadTicket>(`${API_V1}/files/${id}/download-url`, { method: 'POST', signal }),
  startMultipart: (payload: MultipartStart, signal?: AbortSignal) => fetchApi<MultipartTicket>(`${API_V1}/files/multipart/uploads`, { method: 'POST', body: JSON.stringify(payload), signal }),
  multipartPartUrl: (id: string, number: number, signal?: AbortSignal) => fetchApi<PartTicket>(`${API_V1}/files/${id}/multipart/parts/${number}/url`, { method: 'POST', signal }),
  confirmPart: (id: string, number: number, signal?: AbortSignal) => fetchApi<PartTicket>(`${API_V1}/files/${id}/multipart/parts/${number}/confirm`, { method: 'POST', signal }),
  completeMultipart: (id: string, signal?: AbortSignal) => fetchApi<FileMetadata>(`${API_V1}/files/${id}/multipart/complete`, { method: 'POST', signal }),
  abortMultipart: (id: string) => fetchApi<FileMetadata>(`${API_V1}/files/${id}/multipart/abort`, { method: 'POST' }),
  multipartProgress: (id: string, signal?: AbortSignal) => fetchApi<MultipartProgress>(`${API_V1}/files/${id}/multipart/progress`, { method: 'POST', signal }),
  resumeMultipart: (id: string, checksums: string[], signal?: AbortSignal) => fetchApi<MultipartTicket>(`${API_V1}/files/${id}/multipart/resume`, { method: 'POST', body: JSON.stringify({ checksums }), signal }),
  completeUpload: (id: string) => fetchApi<FileMetadata>(`${API_V1}/files/${id}/complete`, { method: 'POST' }),
  files: (folder_id: string | null = null, offset = 0) => fetchApi<FilePage>(`${API_V1}/files?offset=${offset}&limit=25${folder_id ? `&folder_id=${encodeURIComponent(folder_id)}` : ''}`),
  folders: (parent_id: string | null = null, offset = 0, signal?: AbortSignal) => fetchApi<FolderPage>(`${API_V1}/folders?offset=${offset}&limit=25${parent_id ? `&parent_id=${encodeURIComponent(parent_id)}` : ''}`, { signal }),
  createFolder: (name: string, parent_id: string | null) => fetchApi<Folder>(`${API_V1}/folders`, {
    method: 'POST', body: JSON.stringify({ name, parent_id }),
  }),
  renameFolder: (id: string, name: string) => fetchApi<Folder>(`${API_V1}/folders/${id}`, {
    method: 'PATCH', body: JSON.stringify({ name }),
  }),
  moveFolder: (id: string, parent_id: string | null) => fetchApi<Folder>(`${API_V1}/folders/${id}/move`, {
    method: 'POST', body: JSON.stringify({ parent_id }),
  }),
  getHealth: () => fetchApi<HealthResponse>(`${API_V1}/health`),
  getReadiness: () => fetchApi<ReadinessResponse>(`${API_V1}/health/ready`),
  register: (payload: RegisterPayload) =>
    fetchApi<TokenResponse>(`${API_V1}/auth/register`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  login: (payload: LoginPayload) =>
    fetchApi<TokenResponse>(`${API_V1}/auth/login`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  refresh: refreshSession,
  logout: () =>
    fetchApi<void>(`${API_V1}/auth/logout`, {
      method: 'POST',
    }, false),
  me: () => fetchApi<User>(`${API_V1}/auth/me`),
  updateProfile: (full_name: string) => fetchApi<User>(`${API_V1}/users/me`, {
    method: 'PATCH', body: JSON.stringify({ full_name }),
  }),
  organization: () => fetchApi<Tenant>(`${API_V1}/organizations/current`),
  workspaces: (offset = 0) => fetchApi<Workspace[]>(`${API_V1}/organizations?offset=${offset}&limit=25`),
  createWorkspace: (name: string) => fetchApi<TokenResponse>(`${API_V1}/organizations`, {
    method: 'POST', body: JSON.stringify({ name }),
  }, false),
  switchWorkspace: (id: string) => fetchApi<TokenResponse>(`${API_V1}/organizations/${id}/switch`, {
    method: 'POST',
  }, false),
  acceptExistingInvitation: (token: string) => fetchApi<Tenant>(`${API_V1}/organizations/invitations/accept-existing`, {
    method: 'POST', body: JSON.stringify({ token }),
  }, false),
  transferOwnership: (user_id: string, password: string, confirmation: string) => fetchApi<void>(`${API_V1}/organizations/current/ownership`, {
    method: 'POST', body: JSON.stringify({ user_id, password, confirmation }),
  }, false),
  renameOrganization: (name: string) => fetchApi<Tenant>(`${API_V1}/organizations/current`, {
    method: 'PATCH', body: JSON.stringify({ name }),
  }),
  members: (offset = 0, limit = 25) => fetchApi<Member[]>(
    `${API_V1}/organizations/current/members?offset=${offset}&limit=${limit}`,
  ),
  changeRole: (id: string, role: 'admin' | 'member') => fetchApi<Member>(
    `${API_V1}/organizations/current/members/${id}`, {
      method: 'PATCH', body: JSON.stringify({ role }),
    },
  ),
  removeMember: (id: string) => fetchApi<void>(`${API_V1}/organizations/current/members/${id}`, {
    method: 'DELETE',
  }),
  invite: (email: string, role: 'admin' | 'member') => fetchApi<InvitationCreated>(
    `${API_V1}/organizations/current/invitations`, {
      method: 'POST', body: JSON.stringify({ email, role }),
    },
  ),
  invitations: (offset = 0) => fetchApi<Invitation[]>(
    `${API_V1}/organizations/current/invitations?offset=${offset}&limit=25`,
  ),
  revokeInvitation: (id: string) => fetchApi<void>(
    `${API_V1}/organizations/current/invitations/${id}`, { method: 'DELETE' },
  ),
  acceptInvitation: (payload: AcceptInvitationPayload) => fetchApi<TokenResponse>(
    `${API_V1}/organizations/invitations/accept`, {
      method: 'POST', body: JSON.stringify(payload),
    }, false,
  ),
  requestRecovery: (email: string, purpose: 'verify' | 'reset') => fetchApi<{ detail: string }>(
    `${API_V1}/account/recovery-request`, { method: 'POST', body: JSON.stringify({ email, purpose }) }, false,
  ),
  verifyEmail: (token: string) => fetchApi<{ detail: string }>(`${API_V1}/account/verify`, {
    method: 'POST', body: JSON.stringify({ token }),
  }, false),
  resetPassword: (token: string, password: string) => fetchApi<{ detail: string }>(`${API_V1}/account/reset-password`, {
    method: 'POST', body: JSON.stringify({ token, password }),
  }, false),
  requestEmailChange: (email: string, password: string) => fetchApi<{ detail: string }>(`${API_V1}/account/email-change`, {
    method: 'POST', body: JSON.stringify({ email, password }),
  }),
  confirmEmailChange: (token: string, password: string) => fetchApi<{ detail: string }>(`${API_V1}/account/confirm-email`, {
    method: 'POST', body: JSON.stringify({ token, password }),
  }),
  sessions: (offset = 0) => fetchApi<AccountSession[]>(`${API_V1}/account/sessions?offset=${offset}&limit=25`),
  revokeSession: (id: string) => fetchApi<void>(`${API_V1}/account/sessions/${id}`, { method: 'DELETE' }),
  signOutAll: (password: string) => fetchApi<void>(`${API_V1}/account/sign-out-all`, {
    method: 'POST', body: JSON.stringify({ password }),
  }),
  emailDeliveries: () => fetchApi<EmailDelivery[]>(`${API_V1}/account/email-deliveries`),
  deleteAccount: (password: string, confirmation: string) => fetchApi<void>(`${API_V1}/account`, {
    method: 'DELETE', body: JSON.stringify({ password, confirmation }),
  }),
};

export async function publicShareRequest<T>(action: 'access' | 'download-url', payload: { token: string; password: string }, signal?: AbortSignal): Promise<T> {
  // Public capabilities never inherit the signed-in user's cookies or authorization.
  const response = await fetch(`${API_V1}/shares/${action}`, { method: 'POST', body: JSON.stringify(payload),
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, credentials: 'omit',
    referrerPolicy: 'no-referrer', cache: 'no-store', signal });
  if (!response.ok) throw new ApiRequestError(await parseError(response), response.status);
  return response.json();
}

export async function uploadBrowserFile(file: File, folderId: string | null, requestId: string,
  retryId: string | null, signal: AbortSignal, progress: (message: string) => void) {
  const epoch = sessionEpoch;
  const current = () => { if (signal.aborted || sessionEpoch !== epoch) throw new Error('Upload interrupted by navigation or workspace change.'); };
  current(); progress('Checking file…');
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', await file.arrayBuffer()));
  const checksum = btoa(String.fromCharCode(...digest)); current();
  if (retryId) {
    try {
      const completed = await api.completeUpload(retryId); current();
      if (completed.checksum_sha256 !== checksum || completed.size_bytes !== file.size) throw new Error('Choose the same file content to retry this upload.');
      return completed;
    }
    catch (error) { current(); if (!(error instanceof ApiRequestError) || error.status !== 409) throw error; }
  }
  const ticket = retryId ? await api.retryUpload(retryId, checksum) : await api.startUpload({
    name: file.name, folder_id: folderId, declared_size_bytes: file.size,
    declared_content_type: /^[A-Za-z0-9!#$&^_.+-]+\/[A-Za-z0-9!#$&^_.+-]+$/.test(file.type) ? file.type : null,
    checksum_sha256: checksum, request_id: requestId,
  });
  current();
  if (ticket.file.declared_size_bytes !== file.size) throw new Error('Choose the same file content to retry this upload.');
  progress('Transferring file…');
  try {
    // Object storage never receives CloudVault cookies or bearer credentials.
    const result = await fetch(ticket.upload_url, { method: 'PUT', body: file, headers: ticket.headers,
      credentials: 'omit', referrerPolicy: 'no-referrer', signal });
    current();
    if (!result.ok && result.status !== 412) throw new Error('Object transfer failed.');
  } catch (error) {
    current();
    // A lost response can follow a successful write. Reconcile through the API.
    try { const completed = await api.completeUpload(ticket.file.id); current(); return completed; }
    catch { throw error; }
  }
  progress('Verifying upload…'); current();
  const completed = await api.completeUpload(ticket.file.id); current(); return completed;
}


export async function downloadBrowserFile(id: string, signal?: AbortSignal) {
  const epoch = sessionEpoch;
  const ticket = await api.downloadTicket(id, signal);
  if (signal?.aborted || epoch !== sessionEpoch) throw new ApiRequestError('Session changed; try again', 409);
  // Native navigation streams to the browser download manager, without buffering file bytes in the SPA.
  const link = document.createElement('a');
  link.href = ticket.download_url;
  link.referrerPolicy = 'no-referrer';
  link.rel = 'noopener noreferrer';
  link.download = ticket.file.name;
  document.body.append(link);
  try { link.click(); } finally { link.remove(); }
}

export async function uploadMultipartFile(file: File, folderId: string | null, requestId: string,
  partSize: number, maxBytes: number, signal: AbortSignal, progress: (message: string) => void, started?: (id: string) => void, resumeId?: string) {
  const epoch = sessionEpoch;
  const current = () => { if (signal.aborted) throw new DOMException('Upload stopped', 'AbortError'); if (epoch !== sessionEpoch) throw new ApiRequestError('Session changed; try again', 409); };
  current();
  if (resumeId) {
    const saved = await api.multipartProgress(resumeId, signal); current();
    if (saved.file.declared_size_bytes !== file.size) throw new Error('Choose the original file content to resume.');
    partSize = saved.part_size;
    maxBytes = Math.max(maxBytes, saved.file.declared_size_bytes);
  }
  if (!file.size || file.size > maxBytes || partSize < 5 * 1024 * 1024 || partSize > 32 * 1024 * 1024) throw new Error('File exceeds multipart limits.');
  const count = Math.ceil(file.size / partSize);
  if (count > 1024) throw new Error('Too many upload parts.');
  const checksums: string[] = []; const digests: Uint8Array[] = [];
  for (let index = 0; index < count; index++) {
    current(); progress(`Checking part ${index + 1} of ${count}…`);
    const bytes = await file.slice(index * partSize, (index + 1) * partSize).arrayBuffer(); current();
    const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)); current();
    checksums.push(btoa(String.fromCharCode(...digest))); digests.push(digest);
  }
  const combined = new Uint8Array(count * 32); digests.forEach((digest, index) => combined.set(digest, index * 32));
  const expected = btoa(String.fromCharCode(...new Uint8Array(await crypto.subtle.digest('SHA-256', combined)))); current();
  const ticket = resumeId ? await api.resumeMultipart(resumeId, checksums, signal) : await api.startMultipart({ name: file.name, folder_id: folderId, declared_size_bytes: file.size,
    declared_content_type: /^[A-Za-z0-9!#$&^_.+-]+\/[A-Za-z0-9!#$&^_.+-]+$/.test(file.type) ? file.type : null,
    request_id: requestId, part_size: partSize, checksums }, signal); current();
  started?.(ticket.file.id);
  if (ticket.file.status === 'uploaded') {
    if (ticket.file.checksum_sha256 !== expected || ticket.file.size_bytes !== file.size || ticket.file.checksum_kind !== 'sha256-composite') throw new Error('Completed file does not match selected content.');
    return ticket.file;
  }
  if (ticket.part_size !== partSize || ticket.parts.length !== count || ticket.file.declared_size_bytes !== file.size) throw new Error('Invalid multipart plan.');
  for (let index = 0; index < count; index++) {
    let part = ticket.parts[index]; const body = file.slice(index * partSize, (index + 1) * partSize);
    if (part.number !== index + 1 || part.size_bytes !== body.size || part.checksum_sha256 !== checksums[index]) throw new Error('Invalid upload part declaration.');
    if (part.confirmed) continue;
    for (let attempt = 0; attempt < 3; attempt++) {
      current(); progress(`Uploading part ${index + 1} of ${count}…`);
      let failure: unknown;
      try {
        if (!part.upload_url) throw new Error('Part authorization is missing.');
        const result = await fetch(part.upload_url, { method: 'PUT', body, headers: part.headers, credentials: 'omit', referrerPolicy: 'no-referrer', signal }); current();
        if (!result.ok) throw new Error(`Part transfer failed (${result.status}).`);
      } catch (error) { failure = error; current(); }
      try { await api.confirmPart(ticket.file.id, part.number, signal); current(); break; }
      catch (error) {
        current();
        if (attempt === 2) throw failure ?? error;
        part = await api.multipartPartUrl(ticket.file.id, part.number, signal); current();
        if (part.number !== index + 1 || part.size_bytes !== body.size || part.checksum_sha256 !== checksums[index]) throw new Error('Part authorization changed.');
      }
    }
  }
  current(); progress('Verifying multipart completion…');
  const completed = await api.completeMultipart(ticket.file.id, signal); current();
  if (completed.checksum_sha256 !== expected || completed.size_bytes !== file.size || completed.checksum_kind !== 'sha256-composite') throw new Error('Completed file verification changed.');
  return completed;
}
