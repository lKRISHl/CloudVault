import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../app/App';
import { getAccessToken, setAccessToken } from '../services/api';
import type { Member, TokenResponse, User } from '../types';

const baseUser: User = {
  id: 'owner-id', email: 'owner@example.com', full_name: 'Ada Owner', role: 'owner', is_active: true, email_verified: true,
  tenant: { id: 'tenant-id', name: 'Engines', slug: 'engines', created_at: '2026-10-13' },
};
const teamMember: Member = {
  user_id: 'member-id', email: 'member@example.com', full_name: 'Grace Member', role: 'member',
  joined_at: '2026-10-13',
};
const pendingInvitation = {
  id: 'invite-id', email: 'new@example.com', role: 'member', expires_at: '2026-10-20',
};
const respond = (body: unknown, status = 200) => ({
  ok: status >= 200 && status < 300, status, json: async () => body,
}) as Response;

function setupUser() {
  const user = userEvent.setup();
  return {
    type: async (element: HTMLElement, text: string) => {
      await act(async () => { await user.type(element, text); });
    },
    clear: async (element: HTMLElement) => {
      await act(async () => { await user.clear(element); });
    },
    click: async (element: HTMLElement) => {
      await act(async () => { await user.click(element); });
    },
    select: async (element: HTMLElement, value: string) => {
      await act(async () => { await user.selectOptions(element, value); });
    },
  };
}

describe('Organization and profile flows', () => {
  let currentUser: User;
  let members: Member[];
  let invitations: typeof pendingInvitation[];

  beforeEach(() => {
    currentUser = { ...baseUser, tenant: { ...baseUser.tenant! } };
    members = [{ ...teamMember }];
    invitations = [{ ...pendingInvitation }];
    setAccessToken(null);
    window.history.pushState({}, '', '/app/settings');
    vi.stubGlobal('confirm', vi.fn(() => true));
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
      const url = String(input);
      const method = options?.method ?? 'GET';
      const body = options?.body ? JSON.parse(String(options.body)) : {};
      if (url.endsWith('/auth/refresh')) {
        return respond({ access_token: 'token', token_type: 'bearer', expires_in: 900, user: currentUser } satisfies TokenResponse);
      }
      if (url.endsWith('/auth/me')) return respond(currentUser);
      if (url.endsWith('/users/me') && method === 'PATCH') {
        currentUser = { ...currentUser, full_name: body.full_name };
        return respond(currentUser);
      }
      if (url.endsWith('/organizations/current') && method === 'PATCH') {
        currentUser = { ...currentUser, tenant: { ...currentUser.tenant!, name: body.name } };
        return respond(currentUser.tenant);
      }
      if (url.includes('/current/members?')) {
        const offset = Number(new URL(url, window.location.origin).searchParams.get('offset'));
        return respond(members.slice(offset, offset + 25));
      }
      if (url.endsWith('/members/member-id')) {
        if (method === 'PATCH') {
          members = members.map((member) => ({ ...member, role: body.role }));
          return respond(members[0]);
        }
        members = [];
        return respond(undefined, 204);
      }
      if (url.endsWith('/current/invitations') && method === 'POST') {
        const created = { ...pendingInvitation, email: body.email, role: body.role };
        invitations = [created];
        return respond({ ...created, token: 'private-token' }, 201);
      }
      if (url.includes('/current/invitations?')) return respond(invitations);
      if (url.endsWith('/invitations/invite-id') && method === 'DELETE') {
        invitations = [];
        return respond(undefined, 204);
      }
      if (url.includes('/health')) return respond({ status: 'ok' });
      if (url.includes('/organizations?')) return respond([{ tenant: currentUser.tenant, role: currentUser.role }]);
      throw new Error(`Unexpected request ${method} ${url}`);
    }));
  });
  afterEach(() => { vi.unstubAllGlobals(); });

  it('edits the profile and organization with refreshed user data', async () => {
    render(<App />);
    const user = setupUser();
    const name = await screen.findByLabelText('Full name');
    await user.clear(name);
    await user.type(name, 'Updated Owner');
    await user.click(screen.getByRole('button', { name: 'Save profile' }));
    expect(await screen.findByText('Profile saved.')).toBeInTheDocument();
    const org = screen.getByLabelText('Organization name');
    await user.clear(org);
    await user.type(org, 'Updated Organization');
    await user.click(screen.getByRole('button', { name: 'Save organization' }));
    expect(await screen.findByText('Organization saved.')).toBeInTheDocument();
    expect(currentUser.full_name).toBe('Updated Owner');
    expect(currentUser.tenant!.name).toBe('Updated Organization');
  });

  it('creates a private invitation link and revokes it', async () => {
    render(<App />);
    const user = setupUser();
    await user.type(await screen.findByLabelText('Invitation email'), 'new@example.com');
    await user.click(screen.getByRole('button', { name: 'Create invitation' }));
    expect(await screen.findByLabelText('Private invitation link')).toHaveValue(
      `${window.location.origin}/join#token=private-token`,
    );
    await user.click(screen.getByRole('button', { name: 'Revoke invitation for new@example.com' }));
    expect(await screen.findByText('No pending invitations.')).toBeInTheDocument();
  });

  it('changes a member role and removes the member', async () => {
    render(<App />);
    const user = setupUser();
    await user.select(await screen.findByLabelText('Role for member@example.com'), 'admin');
    await waitFor(() => expect(members[0].role).toBe('admin'));
    await user.click(screen.getByRole('button', { name: 'Remove member@example.com' }));
    await waitFor(() => expect(screen.queryByText('Grace Member')).not.toBeInTheDocument());
    expect(window.confirm).toHaveBeenCalled();
  });

  it('shows a member profile and roster without manager controls', async () => {
    currentUser = { ...currentUser, role: 'member' };
    render(<App />);
    expect(await screen.findByText('Grace Member')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save profile' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save organization' })).not.toBeInTheDocument();
    expect(screen.queryByText('Invite someone')).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Remove member@example.com' })).not.toBeInTheDocument();
  });

  it('keeps an API authorization failure visible', async () => {
    const previous = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, options) => {
      if (String(input).endsWith('/users/me') && options?.method === 'PATCH') {
        return respond({ detail: 'Profile update rejected' }, 403);
      }
      return previous(input, options);
    });
    render(<App />);
    const user = setupUser();
    await screen.findByLabelText('Full name');
    await user.click(screen.getByRole('button', { name: 'Save profile' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Profile update rejected');
  });

  it('accepts an invitation, signs in, and removes the token from the URL', async () => {
    window.history.pushState({}, '', '/join#token=private-token');
    vi.mocked(fetch).mockImplementation(async (input) => {
      if (String(input).endsWith('/auth/refresh')) return respond({ detail: 'Missing cookie' }, 401);
      if (String(input).endsWith('/invitations/accept')) {
        return respond({ access_token: 'token', token_type: 'bearer', expires_in: 900, user: baseUser }, 201);
      }
      if (String(input).includes('/organizations?')) return respond([{ tenant: baseUser.tenant, role: baseUser.role }]);
      return respond({ status: 'ok' });
    });
    render(<App />);
    const user = setupUser();
    await user.type(await screen.findByLabelText('Full name'), 'New Member');
    await user.type(screen.getByLabelText('Password'), 'correct-horse');
    await user.click(screen.getByRole('button', { name: 'Join organization' }));
    expect(await screen.findByText('Ada Owner')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/app');
    expect(window.location.hash).toBe('');
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/invitations/accept'), expect.objectContaining({
      body: JSON.stringify({ token: 'private-token', full_name: 'New Member', password: 'correct-horse' }),
    }));
  });

  it('reports expired invitations without signing in', async () => {
    window.history.pushState({}, '', '/join#token=expired-token');
    vi.mocked(fetch).mockResolvedValue(respond({ detail: 'Invalid or expired invitation' }, 400));
    render(<App />);
    const user = setupUser();
    await user.type(await screen.findByLabelText('Full name'), 'New Member');
    await user.type(screen.getByLabelText('Password'), 'correct-horse');
    await user.click(screen.getByRole('button', { name: 'Join organization' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid or expired invitation');
    expect(window.location.pathname).toBe('/join');
  });

  it('reports an incomplete invitation link', async () => {
    window.history.pushState({}, '', '/join');
    vi.mocked(fetch).mockResolvedValue(respond({ detail: 'Missing cookie' }, 401));
    render(<App />);
    expect(await screen.findByRole('alert')).toHaveTextContent('The invitation link is incomplete');
    expect(screen.queryByRole('button', { name: 'Join organization' })).not.toBeInTheDocument();
  });

  it('lets admins invite members without changing roles', async () => {
    currentUser = { ...currentUser, role: 'admin' };
    render(<App />);
    expect(await screen.findByLabelText('Invitation email')).toBeInTheDocument();
    expect(screen.queryByLabelText('Invitation role')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Role for member@example.com')).not.toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Remove member@example.com' })).toBeInTheDocument();
  });

  it('paginates the member roster', async () => {
    members = Array.from({ length: 26 }, (_, index) => ({
      ...teamMember, user_id: `member-${index}`, email: `member${index}@example.com`,
      full_name: `Member ${index}`,
    }));
    render(<App />);
    const user = setupUser();
    expect(await screen.findByText('Member 0')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Next members' }));
    expect(await screen.findByText('Member 25')).toBeInTheDocument();
    expect(screen.queryByText('Member 0')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Previous members' }));
    expect(await screen.findByText('Member 0')).toBeInTheDocument();
  });

  it('returns a removed member to sign in when protected access and refresh are rejected', async () => {
    let refreshes = 0;
    vi.mocked(fetch).mockImplementation(async (input) => {
      if (String(input).endsWith('/auth/refresh') && ++refreshes === 1) {
        return respond({ access_token: 'token', token_type: 'bearer', expires_in: 900, user: baseUser });
      }
      return respond({ detail: 'Organization membership required' }, 401);
    });
    render(<App />);
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument();
    expect(window.location.pathname).toBe('/login');
    expect(getAccessToken()).toBeNull();
  });
});
