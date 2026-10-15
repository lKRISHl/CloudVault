import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api } from '../../services/api';

export function TrashButton({ kind, id, name }: { kind: 'files' | 'folders'; id: string; name: string }) {
  const cache = useQueryClient(); const alive = useRef(true);
  const [busy, setBusy] = useState(false); const [error, setError] = useState('');
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  async function move() {
    setBusy(true); setError('');
    try {
      await api.moveToTrash(kind, id); if (!alive.current) return;
      await cache.invalidateQueries({ predicate: query => ['trash', 'files', 'folders', 'file-search', 'shares', 'permissions'].includes(String(query.queryKey[0])) });
    } catch (failure) { if (alive.current) setError(failure instanceof Error ? failure.message : 'Unable to move to trash'); }
    finally { if (alive.current) setBusy(false); }
  }
  return <span className="inline-block"><button className="secondary-button" disabled={busy} onClick={() => void move()}>Move {name} to trash</button>{error && <span role="alert">{error}</span>}</span>;
}
