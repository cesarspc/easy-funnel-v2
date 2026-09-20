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

/**
 * Demo convenience: sign in automatically so a local walkthrough opens on the
 * dashboard instead of the login form.
 *
 * This is a real login — it posts the configured credentials and receives the
 * normal session cookie — so every admin endpoint behaves exactly as it does
 * for a merchant. It is not an auth bypass, and there is no client-side
 * "pretend to be authenticated" state anywhere.
 *
 * Three conditions gate it, and all three must hold:
 *   - `MODE === "development"`, which is true only under `vite dev`. A
 *     production build is `"production"` and the test runner is `"test"`, so
 *     this cannot ship in a bundle and cannot leak into the suite.
 *   - `VITE_DEMO_AUTOLOGIN` is explicitly turned on.
 *   - Credentials are supplied; they live in `frontend/.env.local`, which is
 *     gitignored.
 */
const DEMO_AUTOLOGIN =
  import.meta.env.MODE === "development" && import.meta.env.VITE_DEMO_AUTOLOGIN === "1";

export function SessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SessionStatus>("checking");
  const [role, setRole] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function resolveSession() {
      try {
        const session = await authApi.getSession();
        if (cancelled) return;
        if (session.authenticated) {
          setStatus("authenticated");
          setRole(session.role ?? null);
          return;
        }
      } catch {
        // `GET /api/auth/session` answers 401 when no cookie is present, and
        // the transport turns that into a thrown ApiError rather than a
        // session object with `authenticated: false`. Both paths mean the same
        // thing here — not signed in — so both fall through together.
        if (cancelled) return;
      }

      if (DEMO_AUTOLOGIN) {
        const username = import.meta.env.VITE_DEMO_USERNAME;
        const password = import.meta.env.VITE_DEMO_PASSWORD;
        if (username && password) {
          try {
            const result = await authApi.login({ username, password });
            if (cancelled) return;
            setStatus(result.authenticated ? "authenticated" : "unauthenticated");
            setRole(result.role ?? null);
            return;
          } catch {
            // A demo that cannot sign in should show the ordinary login screen
            // rather than hang on "checking".
            if (cancelled) return;
          }
        }
      }

      if (cancelled) return;
      setStatus("unauthenticated");
      setRole(null);
    }

    void resolveSession();

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
