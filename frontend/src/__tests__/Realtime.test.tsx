import { act, cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
import { api } from '../services/api';
import { RealtimeProvider, RealtimeStatus, useLiveResource } from '../realtime/RealtimeProvider';
import { deliverUpdate, liveTopicCount, liveTopics, watchTopic } from '../realtime/registry';

const auth = vi.hoisted(() => ({ user: { id: 'user', email_verified: true, tenant: { id: 'tenant' } },
  resetWorkspace: vi.fn(), reloadUser: vi.fn(async () => {}), adoptSession: vi.fn(async () => {}) }));
vi.mock('../auth/AuthContext', () => ({ useAuth: () => auth }));

class Peer {
  static OPEN = 1;
  static instances: Peer[] = [];
  readyState = 0; sent: string[] = [];
  onopen?: () => void; onmessage?: (event: { data: string }) => void;
  onclose?: (event: { code: number }) => void; onerror?: () => void;
  constructor(public url: string) { Peer.instances.push(this); }
  open() { this.readyState = 1; this.onopen?.(); }
  frame(value: unknown) { this.onmessage?.({ data: JSON.stringify(value) }); }
  send(value: string) { this.sent.push(value); }
  close(code = 1000) { this.readyState = 3; this.onclose?.({ code }); }
}

function Probe() {
  const live = useLiveResource({ kind: 'files' }, ['files', 'tenant', 'user']);
  return <p aria-label="Live revision">{live.revision}</p>;
}

afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); Peer.instances = []; auth.resetWorkspace.mockClear(); });

it('resource hooks remain usable without a realtime or query provider', () => {
  render(<Probe />);
  expect(screen.getByLabelText('Live revision')).toHaveTextContent('0');
});

it('deduplicates topics and never delivers a different subscription to a listener', () => {
  const first = vi.fn(); const second = vi.fn(); const same = vi.fn();
  const stops = [watchTopic({ kind: 'files' }, first), watchTopic({ kind: 'folders' }, second), watchTopic({ kind: 'files' }, same)];
  try {
    const topics = liveTopics();
    expect(topics).toHaveLength(2);
    deliverUpdate({ key: topics.find(topic => topic.kind === 'files')!.key, reason: 'changed', progress: [] });
    expect(first).toHaveBeenCalledOnce(); expect(same).toHaveBeenCalledOnce(); expect(second).not.toHaveBeenCalled();
  } finally { stops.forEach(stop => stop()); }
});

it('caps transmitted subscriptions and leaves overflow visible to the fallback controller', () => {
  const stops = Array.from({ length: 9 }, () => watchTopic({ kind: 'files', parent_id: crypto.randomUUID() }, () => {}));
  try { expect(liveTopics()).toHaveLength(8); expect(liveTopicCount()).toBe(9); }
  finally { stops.forEach(stop => stop()); }
});

it('uses a first-frame ticket and clears scope when an authorized subscription becomes unavailable', async () => {
  vi.useFakeTimers(); vi.stubGlobal('WebSocket', Peer);
  vi.spyOn(api, 'realtimeTicket').mockResolvedValue({ ticket: 't'.repeat(43), expires_in: 20 });
  const cache = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidated = vi.spyOn(cache, 'invalidateQueries');
  render(<QueryClientProvider client={cache}><RealtimeProvider><RealtimeStatus /><Probe /></RealtimeProvider></QueryClientProvider>);
  await act(async () => { await Promise.resolve(); });
  const peer = Peer.instances[0];
  expect(peer.url).not.toContain('ticket'); expect(peer.url).not.toContain('token');
  await act(async () => { peer.open(); peer.frame({ type: 'ready', poll_seconds: 3 }); await vi.advanceTimersByTimeAsync(500); });
  expect(JSON.parse(peer.sent[0])).toEqual({ op: 'authenticate', ticket: 't'.repeat(43) });
  const key = JSON.parse(peer.sent.find(value => JSON.parse(value).op === 'subscribe')!).topics[0].key;
  await act(async () => { peer.frame({ type: 'invalidate', key, reason: 'changed', progress: [] }); });
  expect(invalidated).toHaveBeenCalled();
  expect(screen.getByLabelText('Live revision')).toHaveTextContent('1');
  await act(async () => { peer.frame({ type: 'invalidate', key, reason: 'unavailable', progress: [] }); });
  expect(auth.resetWorkspace).toHaveBeenCalledOnce();
  await act(async () => { peer.frame({ type: 'invalidate', key, reason: 'unavailable', progress: [] }); });
  expect(auth.resetWorkspace).toHaveBeenCalledOnce();
});

it('reconnects after heartbeat loss without putting credentials into the URL', async () => {
  vi.useFakeTimers(); vi.stubGlobal('WebSocket', Peer); vi.spyOn(Math, 'random').mockReturnValue(0);
  vi.spyOn(api, 'realtimeTicket').mockResolvedValue({ ticket: 'x'.repeat(43), expires_in: 20 });
  const cache = new QueryClient();
  render(<QueryClientProvider client={cache}><RealtimeProvider><Probe /></RealtimeProvider></QueryClientProvider>);
  await act(async () => { await Promise.resolve(); Peer.instances[0].open(); Peer.instances[0].frame({ type: 'ready' }); });
  await act(async () => { await vi.advanceTimersByTimeAsync(27000); });
  expect(Peer.instances.length).toBeGreaterThan(1);
  expect(Peer.instances[1].url).not.toMatch(/ticket|token/);
});
