import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AdminShell } from "./AdminShell";
import { SessionProvider } from "../auth/SessionContext";

function renderShell(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <SessionProvider>
        <Routes>
          <Route path="/admin" element={<AdminShell />}>
            <Route path="orders" element={<div>Orders content</div>} />
            <Route path="products" element={<div>Products content</div>} />
          </Route>
        </Routes>
      </SessionProvider>
    </MemoryRouter>,
  );
}

describe("AdminShell", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ authenticated: true, role: "admin" }),
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders all primary navigation destinations", async () => {
    renderShell("/admin/orders");

    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(screen.getByRole("link", { name: /Productos/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Landings/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Pedidos/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Fraude/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Analítica/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Tienda/i })).toBeInTheDocument();
  });

  it("marks the current route's nav item as active", async () => {
    renderShell("/admin/orders");
    await waitFor(() => expect(fetch).toHaveBeenCalled());

    const ordersLink = screen.getByRole("link", { name: /Pedidos/i });
    expect(ordersLink.className).toContain("admin-shell__nav-item--active");

    const productsLink = screen.getByRole("link", { name: /Productos/i });
    expect(productsLink.className).not.toContain("admin-shell__nav-item--active");
  });

  it("renders the routed page content inside the shell", async () => {
    renderShell("/admin/products");
    await waitFor(() => expect(screen.getByText("Products content")).toBeInTheDocument());
  });

  it("opens the mobile drawer when the menu toggle is activated", async () => {
    const user = userEvent.setup();
    renderShell("/admin/orders");
    await waitFor(() => expect(fetch).toHaveBeenCalled());

    const toggle = screen.getByRole("button", { name: /Abrir menú de navegación/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });
});
