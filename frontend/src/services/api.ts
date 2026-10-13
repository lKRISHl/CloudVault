import type { AccountSession, AcceptInvitationPayload, EmailDelivery, HealthResponse, Invitation, InvitationCreated, LoginPayload, Member, ReadinessResponse, RegisterPayload, Tenant, TokenResponse, User } from '../types';

const API_BASE = import.meta.env.VITE_API_URL || '';
const API_V1 = `${API_BASE}/api/v1`;

let accessToken: string | null = null;
let refreshPromise: Promise<TokenResponse> | null = null;
const sessionExpiredListeners = new Set<() => void>();

export function onSessionExpired(listener: () => void) {
  sessionExpiredListeners.add(listener);
  return () => { sessionExpiredListeners.delete(listener); };
}

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export function getAccessToken() {
  return accessToken;
}

class ApiRequestError extends Error {
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
    refreshPromise = fetchApi<TokenResponse>(`${API_V1}/auth/refresh`, {
      method: 'POST',
    }, false).then((session) => {
      setAccessToken(session.access_token);
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
    setAccessToken(null);
    return false;
  }
}

async function fetchApi<T>(url: string, options?: RequestInit, retry = true): Promise<T> {
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

  if (response.status === 401 && retry && !url.includes('/auth/refresh') && !url.includes('/auth/login')) {
    const refreshed = await tryRefresh();
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

  return response.json();
}

export const api = {
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
