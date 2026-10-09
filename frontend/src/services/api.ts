import type { HealthResponse, LoginPayload, ReadinessResponse, RegisterPayload, TokenResponse, User } from '../types';

const API_BASE = import.meta.env.VITE_API_URL || '';
const API_V1 = `${API_BASE}/api/v1`;

let accessToken: string | null = null;

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

async function tryRefresh(): Promise<boolean> {
  const response = await fetch(`${API_V1}/auth/refresh`, {
    method: 'POST',
    credentials: 'include',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    setAccessToken(null);
    return false;
  }
  const data = (await response.json()) as TokenResponse;
  setAccessToken(data.access_token);
  return true;
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
  refresh: () =>
    fetchApi<TokenResponse>(`${API_V1}/auth/refresh`, {
      method: 'POST',
    }, false),
  logout: () =>
    fetchApi<void>(`${API_V1}/auth/logout`, {
      method: 'POST',
    }, false),
  me: () => fetchApi<User>(`${API_V1}/auth/me`),
};
