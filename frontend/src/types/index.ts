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
