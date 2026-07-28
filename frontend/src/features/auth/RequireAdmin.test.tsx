import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RequireAdmin } from "./RequireAdmin";
import { SessionProvider } from "./SessionContext";

function renderGuarded(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <SessionProvider>
        <Routes>
          <Route path="/admin/login" element={<div>Login screen</div>} />
          <Route
            path="/admin/orders"
            element={
              <RequireAdmin>
                <div>Orders screen</div>
              </RequireAdmin>
            }
          />
        </Routes>
      </SessionProvider>
    </MemoryRouter>,
  );
}

describe("RequireAdmin", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("redirects to /admin/login when the session is unauthenticated", async () => {
    beforeEachUnauthenticated();
    renderGuarded("/admin/orders");

    await waitFor(() => expect(screen.getByText("Login screen")).toBeInTheDocument());
  });

  it("renders the guarded content once the session resolves as authenticated", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ authenticated: true, role: "admin" }),
      }),
    );

    renderGuarded("/admin/orders");

    await waitFor(() => expect(screen.getByText("Orders screen")).toBeInTheDocument());
  });
});

function beforeEachUnauthenticated() {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: "Not authenticated" }),
    }),
  );
}
