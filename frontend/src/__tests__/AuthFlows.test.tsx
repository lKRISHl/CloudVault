import { StrictMode } from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../app/App';
import { api, getAccessToken, setAccessToken } from '../services/api';

const session = {
  access_token: 'access-token', token_type: 'bearer', expires_in: 900,
  user: {
    id: 'user-id', email: 'ada@example.com', full_name: 'Ada Lovelace', role: 'owner',
    is_active: true,
    tenant: { id: 'tenant-id', name: 'Engines', slug: 'engines', created_at: '2026-10-13' },
  },
};

const response = (body: unknown, status = 200) => ({
  ok: status >= 200 && status < 300, status, json: async () => body,
});

function setupUser() {
  const user = userEvent.setup();
  return {
    type: async (element: HTMLElement, text: string) => {
      await act(async () => { await user.type(element, text); });
    },
    click: async (element: HTMLElement) => {
      await act(async () => { await user.click(element); });
    },
  };
}

describe('Authentication flows', () => {
  beforeEach(() => {
    setAccessToken(null);
    window.history.pushState({}, '', '/login');
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('/health')) return response({ status: 'ok', version: '0.1.0' });
      return response({ detail: 'Refresh token missing' }, 401);
    }));
  });
  afterEach(() => { vi.unstubAllGlobals(); });

  it('redirects an unauthenticated visitor away from the protected route', async () => {
    window.history.pushState({}, '', '/app');
    render(<App />);
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument();
    expect(window.location.pathname).toBe('/login');
  });

  it('signs in, opens the protected page, then signs out', async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith('/login')) return response(session) as Response;
      if (url.endsWith('/logout')) return response(undefined, 204) as Response;
      if (url.includes('/health')) return response({ status: 'ok' }) as Response;
      return response({ detail: 'Refresh token missing' }, 401) as Response;
    });
    render(<App />);
    const user = setupUser();
    await user.type(await screen.findByLabelText('Email'), 'ada@example.com');
    await user.type(screen.getByLabelText('Password'), 'correct-horse');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText('Ada Lovelace')).toBeInTheDocument();
    expect(getAccessToken()).toBe('access-token');
    expect(window.location.pathname).toBe('/app');
    await user.click(screen.getByRole('button', { name: 'Sign out' }));
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument();
    expect(getAccessToken()).toBeNull();
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/auth/login'), expect.objectContaining({
      body: JSON.stringify({ email: 'ada@example.com', password: 'correct-horse' }),
      credentials: 'include',
    }));
  });

  it('registers a workspace and enters the protected page', async () => {
    window.history.pushState({}, '', '/register');
    vi.mocked(fetch).mockImplementation(async (input) => {
      if (String(input).endsWith('/register')) return response(session) as Response;
      if (String(input).includes('/health')) return response({ status: 'ok' }) as Response;
      return response({ detail: 'Refresh token missing' }, 401) as Response;
    });
    render(<App />);
    const user = setupUser();
    await user.type(await screen.findByLabelText('Full name'), 'Ada Lovelace');
    await user.type(screen.getByLabelText('Workspace name'), 'Engines');
    await user.type(screen.getByLabelText('Email'), 'ada@example.com');
    await user.type(screen.getByLabelText('Password'), 'correct-horse');
    await user.click(screen.getByRole('button', { name: 'Create workspace' }));
    expect(await screen.findByText('Ada Lovelace')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/app');
  });

  it('shows failed login without granting access', async () => {
    vi.mocked(fetch).mockResolvedValue(response({ detail: 'Invalid email or password' }, 401) as Response);
    render(<App />);
    const user = setupUser();
    await user.type(await screen.findByLabelText('Email'), 'ada@example.com');
    await user.type(screen.getByLabelText('Password'), 'wrong-password');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText('Invalid email or password')).toBeInTheDocument();
    expect(getAccessToken()).toBeNull();
    expect(window.location.pathname).toBe('/login');
  });

  it('restores the session once under StrictMode', async () => {
    vi.mocked(fetch).mockImplementation(async (input) => {
      if (String(input).endsWith('/refresh')) return response(session) as Response;
      return response({ status: 'ok' }) as Response;
    });
    render(<StrictMode><App /></StrictMode>);
    expect(await screen.findByText('Ada Lovelace')).toBeInTheDocument();
    expect(vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith('/refresh'))).toHaveLength(1);
  });

  it('shares one refresh between simultaneous unauthorized requests and retries both', async () => {
    setAccessToken('expired-token');
    let finishRefresh: (value: Response) => void = () => { throw new Error('Refresh not started'); };
    vi.mocked(fetch).mockImplementation(async (input, options) => {
      if (String(input).endsWith('/refresh')) {
        return new Promise<Response>((resolve) => { finishRefresh = resolve; });
      }
      const headers = new Headers(options?.headers);
      return headers.get('Authorization') === 'Bearer access-token'
        ? response(session.user) as Response
        : response({ detail: 'Expired' }, 401) as Response;
    });
    const requests = [api.me(), api.me()];
    await waitFor(() => {
      expect(vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith('/refresh'))).toHaveLength(1);
    });
    finishRefresh(response(session) as Response);
    expect(await Promise.all(requests)).toEqual([session.user, session.user]);
    expect(getAccessToken()).toBe('access-token');
  });
});
