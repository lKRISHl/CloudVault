import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { QueryClientContext, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { useAuth } from '../auth/AuthContext';
import { api, ApiRequestError } from '../services/api';
import { deliverUpdate, liveTopicCount, liveTopics, watchTopic, watchTopicSet, type LiveTopic, type LiveUpdate } from './registry';

const protectedKeys = new Set(['groups', 'group-members', 'group-candidates', 'permission-groups', 'storage-usage', 'files', 'folders', 'versions', 'file-search', 'permissions', 'shares',
  'trash', 'organization', 'workspaces', 'permission-candidates', 'folder-destination', 'move-file-destination', 'restore-destination']);
type LiveState = { status: 'connecting' | 'live' | 'offline' | 'limited'; notice: string; progress: Record<string, number> };
const LiveContext = createContext<LiveState | null>(null);

function socketUrl() {
  const base = import.meta.env.VITE_API_URL || location.origin;
  const url = new URL('/api/v1/realtime/connect', base);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}

export function RealtimeProvider({ children }: { children: ReactNode }) {
  const auth = useAuth(); const cache = useQueryClient();
  const realm = auth.user?.email_verified ? `${auth.user.id}:${auth.user.tenant?.id ?? 'account'}` : '';
  const realmRef = useRef(realm); realmRef.current = realm;
  const callbacks = useRef(auth); callbacks.current = auth;
  const [state, setState] = useState<LiveState & { realm: string }>({ realm: '', status: 'offline', notice: '', progress: {} });

  useEffect(() => {
    if (!realm || typeof WebSocket === 'undefined') return;
    let active = true; let socket: WebSocket | undefined;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let subscribeTimer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0; let lastMessage = Date.now(); let openedAt = Date.now(); let authenticated = false;
    const denied = new Set<string>();
    const tickets = new AbortController();
    const current = () => active && realmRef.current === realm;
    const status = (value: LiveState['status']) => {
      if (current()) setState(previous => ({ realm, status: value,
        notice: previous.realm === realm ? previous.notice : '', progress: previous.realm === realm ? previous.progress : {} }));
    };
    const subscribe = () => {
      clearTimeout(subscribeTimer);
      subscribeTimer = setTimeout(() => {
        if (current() && authenticated && socket?.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ op: 'subscribe', topics: liveTopics() }));
          status(liveTopicCount() > 8 ? 'limited' : 'live');
        }
      }, 500);
    };
    const stopTopics = watchTopicSet(subscribe);

    // A denied REST refetch must not leave previously cached private data/modal state visible.
    const stopCache = cache.getQueryCache().subscribe(event => {
      if (!current() || event.type !== 'updated' || event.action.type !== 'error') return;
      const query = event.query;
      if (protectedKeys.has(String(query.queryKey[0])) && query.state.data !== undefined &&
          query.state.error instanceof ApiRequestError && [401, 403, 404, 410, 423].includes(query.state.error.status)) {
        callbacks.current.resetWorkspace();
      }
    });

    const connect = async () => {
      if (!current()) return;
      status('connecting');
      try {
        const grant = await api.realtimeTicket(tickets.signal);
        if (!current()) return;
        const peer = new WebSocket(socketUrl()); socket = peer; authenticated = false;
        peer.onopen = () => {
          if (!current()) { peer.close(); return; }
          lastMessage = Date.now(); openedAt = Date.now();
          peer.send(JSON.stringify({ op: 'authenticate', ticket: grant.ticket }));
        };
        peer.onmessage = event => {
          if (!current() || socket !== peer) return;
          if (typeof event.data !== 'string' || event.data.length > 65536) { peer.close(1002); return; }
          try {
            const message = JSON.parse(event.data);
            lastMessage = Date.now();
            if (message.type === 'ready') {
              authenticated = true; status('live'); subscribe();
              void cache.invalidateQueries({ predicate: query => protectedKeys.has(String(query.queryKey[0])), refetchType: 'active' });
            } else if (message.type === 'identity_changed') {
              void callbacks.current.reloadUser().catch(() => {});
            } else if (message.type === 'invalidate' && typeof message.key === 'string' &&
                ['changed', 'unavailable'].includes(message.reason) && Array.isArray(message.progress) && message.progress.length <= 25 &&
                message.progress.every((row: { id?: unknown; bytes?: unknown }) => typeof row.id === 'string' && row.id.length <= 36 && Number.isSafeInteger(row.bytes) && Number(row.bytes) >= 0)) {
              const update = message as LiveUpdate;
              const description = deliverUpdate(update);
              if (!description) return;
              if (message.reason === 'unavailable') {
                setState(previous => ({ ...previous, progress: {} }));
                if (!denied.has(description)) { denied.add(description); callbacks.current.resetWorkspace(); }
              } else {
                denied.delete(description);
                setState(previous => ({ realm, status: liveTopicCount() > 8 ? 'limited' : 'live',
                  notice: 'A subscribed view changed. Current access and status are being refreshed.',
                  progress: Object.fromEntries([...Object.entries(previous.realm === realm ? previous.progress : {}),
                    ...update.progress.map(row => [row.id, row.bytes] as [string, number])].slice(-200)) }));
              }
            } else if (message.type === 'heartbeat') {
              if (Date.now() - openedAt >= 15000) attempt = 0;
            } else peer.close(1002);
          } catch { peer.close(1002); }
        };
        peer.onerror = () => { /* Close handles bounded retry; never expose native/socket details. */ };
        peer.onclose = event => {
          if (!current() || socket !== peer) return;
          socket = undefined; authenticated = false; status('offline');
          if (event.code === 4401) {
            void callbacks.current.adoptSession();
            return;
          }
          const delay = Math.min(30000, 1000 * 2 ** Math.min(attempt++, 5)) + Math.random() * 500;
          retry = setTimeout(() => void connect(), delay);
        };
      } catch {
        if (!current()) return;
        status('offline');
        const delay = Math.min(30000, 1000 * 2 ** Math.min(attempt++, 5)) + Math.random() * 500;
        retry = setTimeout(() => void connect(), delay);
      }
    };
    void connect();
    const watchdog = setInterval(() => {
      if (socket?.readyState === WebSocket.OPEN && Date.now() - lastMessage > 20000) socket.close(1000);
    }, 5000);
    const fallback = setInterval(() => {
      if (current() && (!authenticated || socket?.readyState !== WebSocket.OPEN || liveTopicCount() > 8)) {
        void callbacks.current.reloadUser().catch(() => {});
        void cache.invalidateQueries({ predicate: query => protectedKeys.has(String(query.queryKey[0])), refetchType: 'active' });
      }
    }, 15000);
    return () => {
      active = false; tickets.abort(); stopTopics(); stopCache();
      clearTimeout(retry); clearTimeout(subscribeTimer); clearInterval(watchdog); clearInterval(fallback);
      socket?.close(1000);
    };
  }, [realm, cache]);

  const value: LiveState | null = !realm ? null : state.realm === realm ? state : { status: 'connecting', notice: '', progress: {} };
  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>;
}

export function useLiveResource(topic: LiveTopic, queryKey?: QueryKey, enabled = true) {
  const live = useContext(LiveContext); const cache = useContext(QueryClientContext);
  const [revision, setRevision] = useState(0);
  const description = JSON.stringify(topic); const query = JSON.stringify(queryKey ?? []);
  const connected = live !== null;
  useEffect(() => {
    if (!connected || !enabled) return;
    return watchTopic(JSON.parse(description), () => {
      setRevision(value => value + 1);
      const key = JSON.parse(query) as QueryKey;
      if (key.length) void cache?.invalidateQueries({ queryKey: key, refetchType: 'active' });
    });
  }, [connected, enabled, description, query, cache]);
  return { revision, progress: live?.progress ?? {} };
}

export function RealtimeStatus() {
  const live = useContext(LiveContext);
  if (!live) return null;
  return <aside className="text-sm text-slate-500" aria-label="Live updates">
    <p>{live.status === 'live' ? 'Live updates connected' : live.status === 'limited' ? 'Some views use periodic refresh' : 'Live updates reconnecting; periodic and manual refresh remain available'}</p>
    <p aria-live="polite">{live.notice}</p>
  </aside>;
}
