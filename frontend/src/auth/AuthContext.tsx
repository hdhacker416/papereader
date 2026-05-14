import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { authApi } from '../api/services';
import { AuthUser } from '../types';

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name?: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    authApi.me()
      .then((response) => {
        if (!cancelled) {
          setUser(response.user);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setUser(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    loading,
    login: async (email: string, password: string) => {
      const response = await authApi.login({ email, password });
      setUser(response.user);
    },
    register: async (email: string, password: string, name?: string) => {
      const response = await authApi.register({ email, password, name });
      setUser(response.user);
    },
    logout: async () => {
      await authApi.logout();
      setUser(null);
    },
  }), [loading, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error('useAuth must be used inside AuthProvider');
  }
  return value;
};
