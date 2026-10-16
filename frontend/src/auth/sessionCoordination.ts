/** Only invalidation signals cross tabs. Tokens, user records and credentials stay in memory. */
type Signal = { version: 1; sender: string; nonce: string; kind: 'changing' | 'changed' };
const storageKey = 'cloudvault.session.signal.v1';
const sender = crypto.randomUUID();
let channel: BroadcastChannel | null = null;
const listeners = new Set<(kind: Signal['kind']) => void>();
const seen = new Set<string>();

function receive(value: unknown) {
  if (!value || typeof value !== 'object') return;
  const signal = value as Partial<Signal>;
  if (signal.version !== 1 || typeof signal.sender !== 'string' || signal.sender.length > 80 || signal.sender === sender || typeof signal.nonce !== 'string' ||
      signal.nonce.length > 80 || !['changing', 'changed'].includes(signal.kind ?? '') || seen.has(signal.nonce)) return;
  seen.add(signal.nonce);
  if (seen.size > 100) seen.delete(seen.values().next().value!);
  listeners.forEach(listener => listener(signal.kind!));
}

export function watchSessionChanges(listener: (kind: Signal['kind']) => void) {
  if (!listeners.size) {
    if (typeof BroadcastChannel !== 'undefined') {
      try {
        channel = new BroadcastChannel(storageKey);
        channel.onmessage = event => receive(event.data);
      } catch { channel = null; }
    }
    window.addEventListener('storage', storageChanged);
  }
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
    if (!listeners.size) { channel?.close(); channel = null; window.removeEventListener('storage', storageChanged); }
  };
}

function storageChanged(event: StorageEvent) {
  if (event.key !== storageKey || !event.newValue || event.newValue.length > 1000) return;
  try { receive(JSON.parse(event.newValue)); } catch { /* Ignore malformed local notifications. */ }
}

export function publishSessionChange(kind: Signal['kind']) {
  const value: Signal = { version: 1, sender, nonce: crypto.randomUUID(), kind };
  try { channel?.postMessage(value); } catch { /* Sign-in must work with blocked channels. */ }
  try { localStorage.setItem(storageKey, JSON.stringify(value)); } catch { /* Storage may be disabled. */ }
}

export async function withSessionLock<T>(operation: () => Promise<T>): Promise<T> {
  // Server token rotation remains atomic without Web Locks; competing unsupported tabs
  // can fail closed and require sign-in. Never implement a non-atomic localStorage mutex.
  if (typeof navigator !== 'undefined' && navigator.locks) {
    return await navigator.locks.request('cloudvault.session.cookie.v1', operation);
  }
  return operation();
}
