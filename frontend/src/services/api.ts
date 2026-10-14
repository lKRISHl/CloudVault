import type { AccountSession, AcceptInvitationPayload, EmailDelivery, HealthResponse, Invitation, InvitationCreated, LoginPayload, Member, ReadinessResponse, RegisterPayload, Tenant, TokenResponse, User, Workspace, Folder, FolderPage } from '../types';

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

export const api = {
  folders: (parent_id: string | null = null, offset = 0) => fetchApi<FolderPage>(`${API_V1}/folders?offset=${offset}&limit=25${parent_id ? `&parent_id=${encodeURIComponent(parent_id)}` : ''}`),
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
