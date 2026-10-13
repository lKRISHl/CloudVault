import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, beginSessionChange, getAccessToken, setAccessToken } from '../services/api';

const response = (body: unknown, status = 200) => ({ ok: status < 400, status, json: async () => body }) as Response;
const token = (tid: string) => `header.${btoa(JSON.stringify({ tid }))}.signature`;

describe('Workspace request safety', () => {
  afterEach(() => { vi.unstubAllGlobals(); setAccessToken(null); });

  it('rejects an old workspace response after switching rather than returning its data', async () => {
    setAccessToken(token('first'));
    let finish!: (value: Response) => void;
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; })));
    const pending = api.members();
    const rejected = expect(pending).rejects.toThrow('Workspace or session changed');
    beginSessionChange();
    setAccessToken(token('second'));
    finish(response([{ email: 'first-workspace@example.com' }]));
    await rejected;
    expect(getAccessToken()).toBe(token('second'));
  });

  it('does not retry a workspace mutation under a different workspace from a shared refresh cookie', async () => {
    setAccessToken(token('first'));
    const fetchMock = vi.fn(async (url: string) => url.endsWith('/auth/refresh')
      ? response({ access_token: token('second') }) : response({ detail: 'Expired' }, 401));
    vi.stubGlobal('fetch', fetchMock);
    await expect(api.renameOrganization('Sensitive rename')).rejects.toThrow('Expired');
    expect(fetchMock.mock.calls.filter(([url]) => url.endsWith('/organizations/current'))).toHaveLength(1);
    expect(getAccessToken()).toBeNull();
  });

  it('does not let an old refresh response replace the selected workspace token', async () => {
    setAccessToken(null);
    let finish!: (value: Response) => void;
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; })));
    const pending = api.refresh();
    const rejected = expect(pending).rejects.toThrow('Workspace or session changed');
    setAccessToken(token('second'));
    finish(response({ access_token: token('first') }));
    await rejected;
    expect(getAccessToken()).toBe(token('second'));
  });

  it('allows a public verification response while session restoration changes the token', async () => {
    setAccessToken(null);
    let finish!: (value: Response) => void;
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; })));
    const pending = api.verifyEmail('public-link');
    setAccessToken(token('restored'));
    finish(response({ detail: 'Email verified' }));
    expect(await pending).toEqual({ detail: 'Email verified' });
  });
});
