/**
 * Administrator login screen (Requirement 7.1-7.2, 7.9).
 * Sits outside AdminShell: a single graphite panel on the paper ground,
 * the instrument's "power switch" before the panel lights up.
 */

import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../../api";
import { useSession } from "./SessionContext";
import "./LoginPage.css";
import { useStore } from "../store/StoreContext";
import { useAdminTheme } from "../admin/theme";

interface LocationState {
  from?: { pathname: string };
}

export function LoginPage() {
  const { login } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const { store } = useStore();
  // The door matches the room: the merchant's saved theme applies here too, so
  // signing in is not a jump from a white page into a dark panel.
  useAdminTheme();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      await login(username, password);
      const state = location.state as LocationState | null;
      const destination = state?.from?.pathname ?? "/admin";
      navigate(destination, { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError("Usuario o contraseña incorrectos.");
      } else if (err instanceof ApiError && err.status === 429) {
        setError("Demasiados intentos. Espera unos minutos e inténtalo de nuevo.");
      } else {
        setError("No se pudo iniciar sesión. Inténtalo de nuevo.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-screen">
      <div className="login-panel">
        <div className="login-panel__mark" aria-hidden="true">
          <span className="login-panel__led" />
        </div>
        <h1 className="login-panel__title">{store?.store_name ?? "Mi Tienda"}</h1>
        <p className="login-panel__subtitle">Panel de administración</p>

        <form className="login-form" onSubmit={handleSubmit} noValidate>
          <div className="login-form__field">
            <label htmlFor="username" className="login-form__label">
              Usuario
            </label>
            <input
              id="username"
              name="username"
              type="text"
              autoComplete="username"
              required
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className="login-form__input"
              disabled={submitting}
            />
          </div>

          <div className="login-form__field">
            <label htmlFor="password" className="login-form__label">
              Contraseña
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="login-form__input"
              disabled={submitting}
            />
          </div>

          {error && (
            <p className="login-form__error" role="alert">
              {error}
            </p>
          )}

          <button type="submit" className="login-form__submit" disabled={submitting}>
            {submitting ? "Verificando…" : "Iniciar sesión"}
          </button>
        </form>
      </div>
    </main>
  );
}
