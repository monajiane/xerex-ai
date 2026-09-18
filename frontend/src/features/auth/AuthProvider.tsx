/**
 * Administrator session.
 *
 * The access token is kept in memory; the refresh token is an HttpOnly cookie set
 * by the API, so a page reload restores the session silently.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { api, tokenStore } from "@/lib/api/client";
import { authApi } from "@/lib/api/endpoints";
import type { AdminUser } from "@/lib/api/types";

interface AuthContextValue {
  user: AdminUser | null;
  status: "loading" | "authenticated" | "anonymous";
  requiresBootstrap: boolean;
  login: (email: string, password: string) => Promise<void>;
  bootstrap: (email: string, password: string, fullName?: string) => Promise<void>;
  logout: () => Promise<void>;
  isRole: (...roles: AdminUser["role"][]) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<AdminUser | null>(null);
  const [status, setStatus] = useState<"loading" | "authenticated" | "anonymous">("loading");
  const [requiresBootstrap, setRequiresBootstrap] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const restore = async () => {
      try {
        const bootstrap = await authApi.bootstrapStatus();
        if (cancelled) return;
        setRequiresBootstrap(bootstrap.requires_bootstrap);
        if (bootstrap.requires_bootstrap) {
          setStatus("anonymous");
          return;
        }
      } catch {
        // The API may be starting up; continue and let the request below report.
      }

      try {
        // Silent session restore through the HttpOnly refresh cookie.
        const refreshed = await api.refreshSession();
        if (!refreshed) {
          if (!cancelled) setStatus("anonymous");
          return;
        }
        const me = await authApi.me();
        if (cancelled) return;
        setUser(me);
        setStatus("authenticated");
      } catch {
        if (!cancelled) setStatus("anonymous");
      }
    };

    void restore();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const session = await authApi.login({ email, password });
      tokenStore.set(session.tokens);
      setUser(session.user);
      setStatus("authenticated");
      setRequiresBootstrap(false);
      await queryClient.invalidateQueries();
    },
    [queryClient],
  );

  const bootstrap = useCallback(
    async (email: string, password: string, fullName?: string) => {
      const session = await authApi.bootstrap({ email, password, full_name: fullName });
      tokenStore.set(session.tokens);
      setUser(session.user);
      setStatus("authenticated");
      setRequiresBootstrap(false);
      await queryClient.invalidateQueries();
    },
    [queryClient],
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // A revoked or expired session still ends locally.
    }
    tokenStore.set(null);
    setUser(null);
    setStatus("anonymous");
    queryClient.clear();
  }, [queryClient]);

  const isRole = useCallback(
    (...roles: AdminUser["role"][]) => (user ? roles.includes(user.role) : false),
    [user],
  );

  const value = useMemo<AuthContextValue>(
    () => ({ user, status, requiresBootstrap, login, bootstrap, logout, isRole }),
    [user, status, requiresBootstrap, login, bootstrap, logout, isRole],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside <AuthProvider>");
  return context;
}
