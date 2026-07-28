/** Route guard: redirects to /admin/login unless a session is authenticated. */

import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { useSession } from "./SessionContext";

export function RequireAdmin({ children }: { children: ReactNode }) {
  const { status } = useSession();
  const location = useLocation();

  if (status === "checking") {
    return (
      <div className="auth-check" role="status" aria-live="polite">
        <span className="sr-only">Verificando sesión…</span>
      </div>
    );
  }

  if (status === "unauthenticated") {
    return <Navigate to="/admin/login" replace state={{ from: location }} />;
  }

  return <>{children}</>;
}
