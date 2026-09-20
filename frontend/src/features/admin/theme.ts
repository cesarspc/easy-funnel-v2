/**
 * Admin theme preference: "The Instrument Panel" in daylight or at night.
 *
 * Three choices, one resolved value. The merchant picks `light`, `dark`, or
 * `system`; the resolved value is written to `data-theme` on <html>, so
 * `styles/global.css` needs two token blocks instead of duplicating the dark set
 * inside a media query.
 *
 * Scope matters as much as the colors. The attribute exists only while an admin
 * screen is mounted, which keeps the public Landing (`/`, `/p/:slug`) on its own
 * merchant-configured palette: a buyer's page must not go dark because the
 * merchant likes dark tools. Several admin surfaces sit outside one another
 * (the route guard's session check, the login screen, the shell), so the
 * preference lives in one module-level store that all of them read, and the
 * attribute is reference-counted — the last admin screen to unmount removes it,
 * and a login -> dashboard transition never drops it mid-flight.
 *
 * Persistence is best-effort. A private window, blocked site data, or a storage
 * quota error must cost the merchant a remembered preference, never a usable
 * dashboard, so every access is guarded and falls back to the default.
 */

import { useCallback, useLayoutEffect, useSyncExternalStore } from "react";

export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

const STORAGE_KEY = "easy-funnel:admin-theme";

/**
 * Dark is the default because of where the work happens: the dashboard is open
 * for hours beside the storefront, often in the evening, and it is the surface
 * the merchant stares at rather than the one they show a buyer. A merchant who
 * prefers daylight switches once and the choice is remembered.
 */
export const DEFAULT_PREFERENCE: ThemePreference = "dark";

const PREFERENCES: readonly ThemePreference[] = ["light", "dark", "system"];

function isPreference(value: unknown): value is ThemePreference {
  return typeof value === "string" && (PREFERENCES as readonly string[]).includes(value);
}

function readStoredPreference(): ThemePreference {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return isPreference(stored) ? stored : DEFAULT_PREFERENCE;
  } catch {
    return DEFAULT_PREFERENCE;
  }
}

function systemQuery(): MediaQueryList | null {
  // `matchMedia` is missing in some test environments and embedded web views.
  if (typeof window.matchMedia !== "function") return null;
  return window.matchMedia("(prefers-color-scheme: dark)");
}

export function resolveTheme(preference: ThemePreference): ResolvedTheme {
  if (preference !== "system") return preference;
  return systemQuery()?.matches ? "dark" : "light";
}

/* --- Shared store ------------------------------------------------------- */

let preference: ThemePreference = readStoredPreference();
const listeners = new Set<() => void>();

/** How many admin screens are currently mounted (see the reference count note). */
let mounted = 0;

function applyToDocument(): void {
  if (mounted <= 0) return;
  document.documentElement.setAttribute("data-theme", resolveTheme(preference));
}

function onSystemChange(): void {
  applyToDocument();
  // The preference itself did not change, but "Sistema" now resolves elsewhere,
  // so subscribers re-read and repaint against the new resolved value.
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): ThemePreference {
  return preference;
}

function setPreference(next: ThemePreference): void {
  preference = next;
  try {
    window.localStorage.setItem(STORAGE_KEY, next);
  } catch {
    // Storage unavailable: the preference still holds for this session.
  }
  applyToDocument();
  listeners.forEach((listener) => listener());
}

/**
 * Applies the stored preference for as long as the calling admin screen is
 * mounted, and returns the control the theme switch needs.
 *
 * `useLayoutEffect` rather than `useEffect`: the attribute lands before the
 * browser paints, so a dark dashboard never flashes a white panel on first
 * render or on a route change inside `/admin`.
 */
export function useAdminTheme() {
  const current = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  useLayoutEffect(() => {
    mounted += 1;
    applyToDocument();
    const query = systemQuery();
    query?.addEventListener("change", onSystemChange);
    return () => {
      mounted -= 1;
      query?.removeEventListener("change", onSystemChange);
      if (mounted === 0) {
        // The last admin screen is leaving: hand the document back to the
        // storefront, which must never inherit the panel's theme.
        document.documentElement.removeAttribute("data-theme");
      }
    };
  }, []);

  const choose = useCallback((next: ThemePreference) => setPreference(next), []);

  return { preference: current, resolved: resolveTheme(current), choose };
}
