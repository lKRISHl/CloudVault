export interface HealthResponse {
  status: string;
  version: string;
  timestamp: string;
}

export interface ReadinessResponse {
  status: string;
  version: string;
  timestamp: string;
  checks: {
    database: {
      status: string;
      latency_ms?: number;
    };
  };
}

export interface ApiError {
  detail: string;
  status_code: number;
}

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  created_at: string;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: 'owner' | 'admin' | 'member' | null;
  is_active: boolean;
  email_verified: boolean;
  tenant: Tenant | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface RegisterPayload {
  email: string;
  password: string;
  full_name: string;
  tenant_name: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface Member {
  user_id: string;
  email: string;
  full_name: string;
  role: 'owner' | 'admin' | 'member';
  joined_at: string;
}

export interface Invitation {
  id: string;
  email: string;
  role: 'admin' | 'member';
  expires_at: string;
}

export interface InvitationCreated extends Invitation {
  token: string;
}

export interface AcceptInvitationPayload {
  token: string;
  full_name: string;
  password: string;
}

export interface AccountSession {
  id: string;
  created_at: string;
  expires_at: string;
  current: boolean;
}

export interface EmailDelivery {
  id: string;
  purpose: string;
  state: string;
  attempts: number;
  next_attempt_at: string;
}

export interface Workspace {
  tenant: Tenant;
  role: 'owner' | 'admin' | 'member';
}

export interface Folder {
  can_manage?: boolean;
  visibility?: 'workspace' | 'private';
  id: string;
  tenant_id: string;
  parent_id: string | null;
  created_by: string;
  name: string;
  created_at: string;
  updated_at: string;
  can_write: boolean;
}

export interface FolderPage {
  parent: Folder | null;
  breadcrumbs: Folder[];
  items: Folder[];
  offset: number;
  limit: number;
  has_more: boolean;
}

export interface FileMetadata {
  upload_cancelled_at?: string | null;
  legacy_metadata?: boolean;
  current_version?: number;
  version_generation?: number;
  version_keep_last?: number | null;
  can_manage?: boolean;
  visibility?: 'workspace' | 'private';
  upload_method?: 'basic' | 'multipart';
  checksum_kind?: 'sha256' | 'sha256-composite';
  multipart_part_size?: number | null;
  multipart_count?: number | null;
  multipart_state?: 'active' | 'completed' | 'aborted' | null;
  id: string;
  tenant_id: string;
  folder_id: string | null;
  created_by: string;
  name: string;
  declared_size_bytes: number;
  declared_content_type: string | null;
  status: 'pending' | 'uploaded';
  size_bytes?: number | null;
  checksum_sha256?: string | null;
  content_type?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
  can_write: boolean;
}

export interface PreviewResult {
  kind: 'image' | 'pdf' | 'video' | 'text' | 'unsupported';
  file_id: string; version_id: string; version_number: number; generation: number; name: string;
  detected_type: string | null; scan_status: 'unscanned'; image_base64: string | null;
  text: string | null; reason: string | null; width: number | null; height: number | null;
  page: number; pages: number; truncated: boolean;
}

export interface FilePage {
  items: FileMetadata[];
  offset: number;
  limit: number;
  has_more: boolean;
}

export interface PreviewJob {
  id: string; state: 'queued' | 'running' | 'ready' | 'failed' | 'cancelled';
  expires_at: string; preview: PreviewResult | null;
}

export interface FileSearchQuery {
  q?: string; scope?: 'workspace' | 'root' | 'folder'; folder_id?: string;
  status?: 'pending' | 'uploaded'; upload_method?: 'basic' | 'multipart'; created_by?: string;
  declared_content_type?: string; min_bytes?: number; max_bytes?: number;
  sort?: 'name' | 'size' | 'created_at' | 'updated_at'; direction?: 'asc' | 'desc';
  offset?: number; limit?: number;
}
export interface FileSearchItem extends FileMetadata { folder_name?: string | null }
export interface FileSearchPage extends FilePage { items: FileSearchItem[] }

export interface UploadTicket {
  file: FileMetadata;
  upload_url: string;
  headers: Record<string, string>;
  expires_at: string;
}

export interface DownloadTicket { file: FileMetadata; download_url: string; expires_at: string }

export interface PartTicket { number: number; size_bytes: number; checksum_sha256: string; confirmed: boolean; expires_at?: string | null; upload_url?: string | null; headers: Record<string, string> }
export interface MultipartTicket { file: FileMetadata; part_size: number; parts: PartTicket[]; expires_at: string }
export interface MultipartProgress extends MultipartTicket { confirmed_bytes: number; can_resume: boolean }
export interface MultipartStart { name: string; folder_id: string | null; declared_size_bytes: number; declared_content_type: string | null; request_id: string; part_size: number; checksums: string[] }
export interface ShareLink {
  id: string; file_id: string; created_by: string; expires_at: string; revoked_at: string | null;
  allow_download: boolean; password_required: boolean; max_downloads: number | null; download_grants: number; created_at: string;
}
export interface SharedFile { name: string; size_bytes: number; expires_at: string; allow_download: boolean; grants_remaining: number | null }
export interface TrashEntry { id: string; resource_id: string; kind: 'files' | 'folders'; name: string; trashed_at: string; retain_until: string; not_before: string; purge_requested_at: string | null }
export interface FileVersion extends VersionTransferState { id: string; number: number; created_by: string; created_at: string; completed_at: string | null; status: 'pending' | 'uploaded'; size_bytes: number | null; declared_size_bytes: number; checksum_sha256: string | null; checksum_kind: string; is_current: boolean; expires_at: string; can_complete: boolean }
export interface VersionTransferState { upload_method?: 'basic' | 'multipart'; multipart_state?: string | null; part_size?: number | null; cancelled_at?: string | null; prune_requested_at?: string | null; prune_not_before?: string | null }
export interface VersionMultipartTicket { version: FileVersion & VersionTransferState; part_size: number; parts: PartTicket[]; expires_at: string; can_resume: boolean; confirmed_bytes: number }
export interface VersionPage { file: FileMetadata; items: FileVersion[]; offset: number; has_more: boolean; retained_bytes: number; pending_bytes: number }
export interface VersionStart { request_id: string; base_generation: number; declared_size_bytes: number; declared_content_type: string | null; checksum_sha256: string }
export interface VersionTicket { version: FileVersion; upload_url: string | null; headers: Record<string, string>; expires_at: string }
