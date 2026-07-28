/**
 * Administrator session context. Hydrates from GET /api/auth/session on
 * mount so a page refresh doesn't bounce an already-authenticated admin
 * back to the login screen, and exposes login/logout actions used by
 * LoginPage and the dashboard shell.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { ApiError, authApi } from "../../api";

export type SessionStatus = "checking" | "authenticated" | "unauthenticated";

export interface SessionState {
  status: SessionStatus;
  role: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const SessionContext = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SessionStatus>("checking");
  const [role, setRole] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    authApi
      .getSession()
      .then((session) => {
        if (cancelled) return;
        setStatus(session.authenticated ? "authenticated" : "unauthenticated");
        setRole(session.role ?? null);
      })
      .catch(() => {
        if (cancelled) return;
        setStatus("unauthenticated");
        setRole(null);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const result = await authApi.login({ username, password });
    setStatus(result.authenticated ? "authenticated" : "unauthenticated");
    setRole(result.role ?? null);
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch (error) {
      // A failed logout call still ends the local session; the server-side
      // cookie will expire on its own if this request did not land.
      if (!(error instanceof ApiError)) throw error;
    } finally {
      setStatus("unauthenticated");
      setRole(null);
    }
  }, []);

  const value = useMemo<SessionState>(
    () => ({ status, role, login, logout }),
    [status, role, login, logout],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionState {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error("useSession must be used within a SessionProvider");
  }
  return context;
}
