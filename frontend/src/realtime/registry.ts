export type LiveTopic = {
  kind: 'folders' | 'files' | 'file' | 'version' | 'versions' | 'members' | 'invitations' | 'workspaces' | 'trash' | 'permissions' | 'shares' | 'search' | 'preview';
  resource_id?: string; job_id?: string; version_id?: string; parent_id?: string | null;
  resource_kind?: 'files' | 'folders'; offset?: number; search?: Record<string, unknown>;
};
export type LiveUpdate = { key: string; reason: 'changed' | 'unavailable'; progress: { id: string; bytes: number }[] };
type Entry = { key: string; topic: LiveTopic; listeners: Set<(update: LiveUpdate) => void> };
const entries = new Map<string, Entry>();
const watchers = new Set<() => void>();
let serial = 0;

export function watchTopic(topic: LiveTopic, listener: (update: LiveUpdate) => void) {
  const description = JSON.stringify(topic);
  let entry = entries.get(description);
  if (!entry) {
    entry = { key: `live:${++serial}`, topic, listeners: new Set() };
    entries.set(description, entry);
  }
  entry.listeners.add(listener);
  watchers.forEach(watch => watch());
  return () => {
    entry!.listeners.delete(listener);
    if (!entry!.listeners.size) entries.delete(description);
    watchers.forEach(watch => watch());
  };
}

export function liveTopics() {
  return [...entries.values()].slice(0, 8).map(entry => ({ ...entry.topic, key: entry.key }));
}
export function liveTopicCount() { return entries.size; }
export function watchTopicSet(listener: () => void) {
  watchers.add(listener); return () => { watchers.delete(listener); };
}
export function deliverUpdate(update: LiveUpdate): string | undefined {
  const match = [...entries.entries()].find(([, entry]) => entry.key === update.key);
  if (!match) return undefined;
  match[1].listeners.forEach(listener => listener(update));
  return match[0];
}
