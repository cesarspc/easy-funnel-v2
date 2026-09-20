/**
 * AdminShell: the Instrument Panel chrome. Graphite sidebar (fixed nav
 * rows, one lit "current" mark) + slim paper top bar + paper content
 * region. Sidebar collapses to an icon rail below ~1024px and to an
 * off-canvas drawer below ~640px (see DESIGN.md Layout).
 */

import { useState, type ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useSession } from "../auth/SessionContext";
import { useStore } from "../store/StoreContext";
import { ThemeToggle } from "./ThemeToggle";
import { useAdminTheme } from "./theme";
import "./AdminShell.css";

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
}

function Icon({ path }: { path: string }) {
  return (
    <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" focusable="false">
      <path d={path} fill="currentColor" />
    </svg>
  );
}

const NAV_ITEMS: NavItem[] = [
  {
    to: "/admin/products",
    label: "Productos",
    icon: <Icon path="M3 5h14v2H3V5zm0 4h14v2H3V9zm0 4h14v2H3v-2z" />,
  },
  {
    to: "/admin/landings",
    label: "Landings",
    icon: <Icon path="M3 4h14v3H3V4zm0 5h6v7H3V9zm8 0h6v3h-6V9zm0 4h6v3h-6v-3z" />,
  },
  {
    to: "/admin/orders",
    label: "Pedidos",
    icon: <Icon path="M4 3h12v2H4V3zm-1 4h14l-1 10H4L3 7zm5 2v6h2V9H8z" />,
  },
  {
    to: "/admin/fraud",
    label: "Fraude",
    icon: <Icon path="M10 2l7 3v5c0 5-3 8-7 8s-7-3-7-8V5l7-3zm0 4l-1 5h2l-1-5zm0 7a1 1 0 100 2 1 1 0 000-2z" />,
  },
  {
    to: "/admin/analytics",
    label: "Analítica",
    icon: <Icon path="M3 15h2V9H3v6zm5 0h2V5H8v10zm5 0h2v-8h-2v8z" />,
  },
  {
    to: "/admin/store",
    label: "Tienda",
    icon: <Icon path="M3 8l2-5h10l2 5v2h-1v7H4v-7H3V8zm4 2v5h6v-5H7z" />,
  },
];

export function AdminShell() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { logout } = useSession();
  const { store } = useStore();
  const { preference, choose } = useAdminTheme();

  return (
    <div className="admin-shell">
      <aside
        className={`admin-shell__sidebar ${drawerOpen ? "admin-shell__sidebar--open" : ""}`}
      >
        <div className="admin-shell__brand">
          <span className="admin-shell__brand-led" aria-hidden="true" />
          <span className="admin-shell__brand-name">{store?.store_name ?? "Mi Tienda"}</span>
        </div>

        <nav className="admin-shell__nav" aria-label="Navegación principal">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `admin-shell__nav-item ${isActive ? "admin-shell__nav-item--active" : ""}`
              }
              onClick={() => setDrawerOpen(false)}
            >
              <span className="admin-shell__nav-icon">{item.icon}</span>
              <span className="admin-shell__nav-label">{item.label}</span>
            </NavLink>
          ))}
        </nav>
      </aside>

      {drawerOpen && (
        <button
          type="button"
          className="admin-shell__scrim"
          aria-label="Cerrar menú"
          onClick={() => setDrawerOpen(false)}
        />
      )}

      <div className="admin-shell__main">
        <header className="admin-shell__topbar">
          <button
            type="button"
            className="admin-shell__menu-toggle"
            aria-label="Abrir menú de navegación"
            aria-expanded={drawerOpen}
            onClick={() => setDrawerOpen((open) => !open)}
          >
            <svg viewBox="0 0 20 20" width="20" height="20" aria-hidden="true">
              <path
                d="M3 5h14v1.5H3V5zm0 6.75h14v1.5H3v-1.5z"
                fill="currentColor"
              />
            </svg>
          </button>

          <div className="admin-shell__topbar-spacer" />

          <ThemeToggle preference={preference} onChange={choose} />

          <button type="button" className="admin-shell__logout" onClick={() => void logout()}>
            Cerrar sesión
          </button>
        </header>

        <main className="admin-shell__content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
