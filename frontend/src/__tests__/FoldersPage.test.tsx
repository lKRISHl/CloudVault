import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../app/App';
import { setAccessToken } from '../services/api';
import type { Folder } from '../types';

const response = (body: unknown, status = 200) => ({ ok: status < 400, status, json: async () => body }) as Response;
const session = { access_token: 'folder-token', user: { id: 'creator', email: 'creator@example.com', full_name: 'Creator', role: 'member', email_verified: true,
  tenant: { id: 'workspace', name: 'Team', slug: 'team', created_at: '2026-10-14' } } };
const initial: Folder = { id: 'first', tenant_id: 'workspace', parent_id: null, created_by: 'creator', name: 'First', created_at: '2026-10-14', updated_at: '2026-10-14', can_write: true };

describe('Folder browser', () => {
  let folders: Folder[];
  beforeEach(() => {
    setAccessToken(null);
    folders = [{ ...initial }, { ...initial, id: 'target', name: 'Target' }];
    window.history.pushState({}, '', '/app/folders');
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, options?: RequestInit) => {
      const url = String(input); const method = options?.method ?? 'GET';
      const body = options?.body ? JSON.parse(String(options.body)) : {};
      if (url.endsWith('/auth/refresh')) return response(session);
      if (url.endsWith('/files/upload-configuration')) return response({ max_bytes: 104857600, enabled: false });
      if (url.includes('/files?')) return response({ items: [], offset: 0, limit: 25, has_more: false });
      if (url.includes('/folders?')) {
        const parentId = new URL(url, window.location.origin).searchParams.get('parent_id');
        const parent = folders.find((folder) => folder.id === parentId) ?? null;
        return response({ parent, breadcrumbs: parent ? [parent] : [], items: folders.filter((folder) => folder.parent_id === parentId), offset: 0, limit: 25, has_more: false });
      }
      if (url.endsWith('/folders') && method === 'POST') { const created = { ...initial, id: 'created', name: body.name, parent_id: body.parent_id }; folders.push(created); return response(created, 201); }
      if (url.endsWith('/folders/first') && method === 'PATCH') { folders[0] = { ...folders[0], name: body.name }; return response(folders[0]); }
      if (url.endsWith('/folders/first/move')) { folders[0] = { ...folders[0], parent_id: body.parent_id }; return response(folders[0]); }
      throw new Error(`Unexpected request ${method} ${url}`);
    }));
  });
  afterEach(() => vi.unstubAllGlobals());

  it('creates, renames and moves a folder using a browsable destination', async () => {
    render(<App />); const user = userEvent.setup();
    const createName = await screen.findByLabelText('Folder name');
    await act(async () => { await user.type(createName, 'Created'); });
    await act(async () => { await user.click(screen.getByRole('button', { name: 'Create folder' })); });
    expect(await screen.findByRole('status')).toHaveTextContent('Folder created');
    await act(async () => { await user.click(screen.getByRole('button', { name: 'Rename First' })); });
    const name = await screen.findByLabelText('New folder name');
    await act(async () => { await user.clear(name); await user.type(name, 'Renamed'); });
    await act(async () => { await user.click(screen.getByRole('button', { name: 'Save rename' })); });
    expect(await screen.findByRole('status')).toHaveTextContent('Folder renamed');
    await act(async () => { await user.click(screen.getByRole('button', { name: 'Move Renamed' })); });
    const destination = await screen.findByRole('button', { name: 'Open destination Target' });
    await act(async () => { await user.click(destination); });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Move here' })).toBeEnabled());
    await act(async () => { await user.click(screen.getByRole('button', { name: 'Move here' })); });
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Open folder Renamed' })).not.toBeInTheDocument());
    expect(folders[0].parent_id).toBe('target');
  });

  it('allows read-only navigation but hides modification and child creation controls', async () => {
    folders[0].can_write = false;
    render(<App />); const user = userEvent.setup();
    await screen.findByRole('button', { name: 'Open folder First' });
    expect(screen.queryByRole('button', { name: 'Rename First' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Move First' })).not.toBeInTheDocument();
    await act(async () => { await user.click(screen.getByRole('button', { name: 'Open folder First' })); });
    await waitFor(() => expect(screen.getByRole('navigation', { name: 'Folder breadcrumbs' })).toHaveTextContent('First'));
    expect(screen.queryByRole('button', { name: 'Create folder' })).not.toBeInTheDocument();
  });

  it('keeps a server name conflict visible and retains the entered name', async () => {
    const original = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, options) => String(input).endsWith('/folders') && options?.method === 'POST'
      ? response({ detail: 'A folder with this name already exists here' }, 409) : original(input, options));
    render(<App />); const user = userEvent.setup();
    const name = await screen.findByLabelText('Folder name');
    await act(async () => { await user.type(name, 'First'); });
    await act(async () => { await user.click(screen.getByRole('button', { name: 'Create folder' })); });
    expect(await screen.findByRole('alert')).toHaveTextContent('already exists');
    expect(screen.getByLabelText('Folder name')).toHaveValue('First');
  });

  it('shows an inaccessible parent immediately without retrying its 404 response', async () => {
    window.history.pushState({}, '', '/app/folders?folder=missing');
    const original = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation(async (input, options) => String(input).includes('parent_id=missing')
      ? response({ detail: 'Folder not found' }, 404) : original(input, options));
    render(<App />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Folder not found');
    expect(vi.mocked(fetch).mock.calls.filter(([url]) => String(url).includes('parent_id=missing'))).toHaveLength(1);
  });
});
