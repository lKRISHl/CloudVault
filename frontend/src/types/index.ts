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
  role: 'owner' | 'admin' | 'member';
  is_active: boolean;
  tenant: Tenant;
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
