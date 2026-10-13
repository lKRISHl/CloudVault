import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api, beginSessionChange, onSessionExpired, setAccessToken } from '../services/api';
import type { AcceptInvitationPayload, LoginPayload, RegisterPayload, User } from '../types';

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  login: (payload: LoginPayload) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => Promise<void>;
  reloadUser: () => Promise<void>;
  acceptInvitation: (payload: AcceptInvitationPayload) => Promise<void>;
  clearSession: () => void;
  switchWorkspace: (id: string) => Promise<void>;
  createWorkspace: (name: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const cache = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const clearSession = useCallback(() => {
    cache.clear();
    setAccessToken(null);
    setUser(null);
  }, [cache]);

  useEffect(() => onSessionExpired(clearSession), [clearSession]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const session = await api.refresh();
        if (!cancelled) {
          setAccessToken(session.access_token);
          setUser(session.user);
        }
      } catch {
        if (!cancelled) {
          setAccessToken(null);
          setUser(null);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (payload: LoginPayload) => {
    const session = await api.login(payload);
    cache.clear();
    setAccessToken(session.access_token);
    setUser(session.user);
  }, [cache]);

  const register = useCallback(async (payload: RegisterPayload) => {
    const session = await api.register(payload);
    cache.clear();
    setAccessToken(session.access_token);
    setUser(session.user);
  }, [cache]);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      clearSession();
    }
  }, [clearSession]);

  const reloadUser = useCallback(async () => {
    setUser(await api.me());
  }, []);

  const acceptInvitation = useCallback(async (payload: AcceptInvitationPayload) => {
    const session = await api.acceptInvitation(payload);
    cache.clear();
    setAccessToken(session.access_token);
    setUser(session.user);
  }, [cache]);

  const switchWorkspace = useCallback(async (id: string) => {
    beginSessionChange();
    await cache.cancelQueries();
    const session = await api.switchWorkspace(id);
    cache.clear();
    setAccessToken(session.access_token);
    setUser(session.user);
  }, [cache]);

  const createWorkspace = useCallback(async (name: string) => {
    beginSessionChange();
    await cache.cancelQueries();
    const session = await api.createWorkspace(name);
    cache.clear();
    setAccessToken(session.access_token);
    setUser(session.user);
  }, [cache]);

  const value = useMemo(
    () => ({ user, isLoading, login, register, logout, reloadUser, acceptInvitation, clearSession, switchWorkspace, createWorkspace }),
    [user, isLoading, login, register, logout, reloadUser, acceptInvitation, clearSession, switchWorkspace, createWorkspace],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
