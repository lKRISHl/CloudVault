import { afterEach, expect, it, vi } from 'vitest';
import { publishSessionChange, watchSessionChanges, withSessionLock } from '../auth/sessionCoordination';

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); localStorage.clear(); });

it('serializes refresh-cookie operations through the same origin Web Lock', async () => {
  let tail: Promise<unknown> = Promise.resolve();
  const request = vi.fn((_key: string, callback: () => Promise<unknown>) => {
    const result = tail.then(callback); tail = result.catch(() => undefined); return result;
  });
  vi.stubGlobal('navigator', { locks: { request } });
  const order: string[] = []; let release!: () => void;
  const blocked = new Promise<void>(resolve => { release = resolve; });
  const first = withSessionLock(async () => { order.push('first'); await blocked; order.push('first done'); });
  const second = withSessionLock(async () => { order.push('second'); });
  await Promise.resolve(); expect(order).toEqual(['first']);
  release(); await Promise.all([first, second]);
  expect(order).toEqual(['first', 'first done', 'second']);
  expect(request.mock.calls.every(([key]) => key === 'cloudvault.session.cookie.v1')).toBe(true);
});

it('broadcasts only a bounded invalidation signal, without credentials or user metadata', () => {
  const posted: unknown[] = [];
  class Channel { onmessage = null; postMessage(value: unknown) { posted.push(value); } close() {} }
  vi.stubGlobal('BroadcastChannel', Channel);
  const stop = watchSessionChanges(() => {});
  try {
    publishSessionChange('changed');
    expect(posted).toHaveLength(1);
    expect(Object.keys(posted[0] as object).sort()).toEqual(['kind', 'nonce', 'sender', 'version']);
    const serialized = localStorage.getItem('cloudvault.session.signal.v1')!;
    expect(serialized).not.toMatch(/access_token|refresh_token|password|tenant_id|email/);
  } finally { stop(); }
});

it('falls back without pretending localStorage is an atomic cross-tab lock', async () => {
  vi.stubGlobal('navigator', {});
  expect(await withSessionLock(async () => 'server rotation remains authoritative')).toBe('server rotation remains authoritative');
});
