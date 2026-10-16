import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api, ApiRequestError, beginSessionChange, onSessionExpired, refreshSharedSession, setAccessToken } from '../services/api';
import { publishSessionChange, watchSessionChanges, withSessionLock } from './sessionCoordination';
import type { AcceptInvitationPayload, LoginPayload, RegisterPayload, TokenResponse, User } from '../types';

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  scopeRevision: number;
  login: (payload: LoginPayload) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => Promise<void>;
  reloadUser: () => Promise<void>;
  acceptInvitation: (payload: AcceptInvitationPayload) => Promise<void>;
  clearSession: () => void;
  resetWorkspace: () => void;
  adoptSession: () => Promise<void>;
  switchWorkspace: (id: string) => Promise<void>;
  createWorkspace: (name: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const cache = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [scopeRevision, setScopeRevision] = useState(0);
  const generation = useRef(0);
  const clearSession = useCallback(() => {
    generation.current += 1;
    cache.clear(); setAccessToken(null); setUser(null); setIsLoading(false);
    setScopeRevision(value => value + 1);
  }, [cache]);

  const resetWorkspace = useCallback(() => {
    beginSessionChange();
    void cache.cancelQueries(); cache.clear();
    setScopeRevision(value => value + 1);
  }, [cache]);

  const suspend = useCallback(() => {
    const current = ++generation.current;
    setAccessToken(null); void cache.cancelQueries(); cache.clear(); setUser(null);
    setIsLoading(true); setScopeRevision(value => value + 1);
    return current;
  }, [cache]);

  const adoptSession = useCallback(async () => {
    const current = suspend();
    try {
      const session = await refreshSharedSession();
      if (current !== generation.current) return;
      setAccessToken(session.access_token); setUser(session.user);
    } catch {
      if (current === generation.current) { setAccessToken(null); setUser(null); }
    } finally {
      if (current === generation.current) setIsLoading(false);
    }
  }, [suspend]);

  useEffect(() => onSessionExpired(clearSession), [clearSession]);
  useEffect(() => {
    let active = true;
    const current = ++generation.current;
    void api.refresh().then(session => {
      if (active && current === generation.current) {
        setAccessToken(session.access_token); setUser(session.user);
      }
    }).catch(() => {
      if (active && current === generation.current) { setAccessToken(null); setUser(null); }
    }).finally(() => { if (active && current === generation.current) setIsLoading(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const unsubscribe = watchSessionChanges(kind => {
      suspend();
      clearTimeout(timer);
      // Wait behind the writer's cookie lock; recover even if its final signal is lost.
      timer = setTimeout(() => void adoptSession(), kind === 'changed' ? 0 : 300);
    });
    return () => { clearTimeout(timer); unsubscribe(); };
  }, [adoptSession, suspend]);

  const changeSession = useCallback(async (operation: () => Promise<TokenResponse>) => {
    // API session actions use retry=false, avoiding recursive refresh-lock acquisition.
    try { await withSessionLock(async () => {
      const current = ++generation.current;
      beginSessionChange(); void cache.cancelQueries(); cache.clear();
      publishSessionChange('changing');
      try {
        const session = await operation();
        if (current !== generation.current) return;
        setAccessToken(session.access_token); setUser(session.user);
        setScopeRevision(value => value + 1); setIsLoading(false);
      } finally {
        publishSessionChange('changed');
      }
    }); } catch (failure) {
      // A cookie response may have committed while an older client epoch was fenced.
      // Reconcile after releasing the lock; never replay the original mutation.
      if (failure instanceof ApiRequestError && failure.status === 409 && /session changed/i.test(failure.message)) await adoptSession();
      throw failure;
    }
  }, [cache, adoptSession]);

  const login = useCallback((payload: LoginPayload) => changeSession(() => api.login(payload)), [changeSession]);
  const register = useCallback((payload: RegisterPayload) => changeSession(() => api.register(payload)), [changeSession]);
  const acceptInvitation = useCallback((payload: AcceptInvitationPayload) => changeSession(() => api.acceptInvitation(payload)), [changeSession]);
  const switchWorkspace = useCallback((id: string) => changeSession(() => api.switchWorkspace(id)), [changeSession]);
  const createWorkspace = useCallback((name: string) => changeSession(() => api.createWorkspace(name)), [changeSession]);

  const logout = useCallback(async () => {
    await withSessionLock(async () => {
      publishSessionChange('changing'); beginSessionChange();
      try { await api.logout(); }
      finally { clearSession(); publishSessionChange('changed'); }
    });
  }, [clearSession]);

  const reloadUser = useCallback(async () => {
    const next = await api.me();
    if (user && (user.role !== next.role || user.tenant?.id !== next.tenant?.id || user.email_verified !== next.email_verified)) resetWorkspace();
    setUser(next);
  }, [user, resetWorkspace]);

  const value = useMemo(() => ({ user, isLoading, scopeRevision, login, register, logout,
    reloadUser, acceptInvitation, clearSession, switchWorkspace, createWorkspace, resetWorkspace, adoptSession }),
  [user, isLoading, scopeRevision, login, register, logout, reloadUser, acceptInvitation,
    clearSession, switchWorkspace, createWorkspace, resetWorkspace, adoptSession]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within an AuthProvider');
  return context;
}
