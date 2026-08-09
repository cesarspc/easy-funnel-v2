/**
 * Tests for the frontend-only "Dirección 2" field: a reference/complement
 * line (apartment, tower, landmark) shown right after the address field, but
 * never sent to the backend as its own key. It is joined onto `address` with
 * a single space before the order is submitted, so `OrderCreateRequest`
 * carries one complete address string with no backend or schema change.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LandingPage } from "./LandingPage";
import { publicApi } from "../../api";
import type { PublicLanding } from "../../api";

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...actual,
    publicApi: {
      getLanding: vi.fn(),
      recordView: vi.fn().mockResolvedValue(undefined),
      recordCtaClick: vi.fn().mockResolvedValue(undefined),
      createOrder: vi.fn(),
    },
  };
});

function makeLanding(overrides: Partial<PublicLanding> = {}): PublicLanding {
  return {
    landing_id: 1,
    product_id: 1,
    product_name: "Set de Sartenes",
    product_sku: "SET-001",
    product_price: 89900,
    slug: "set-sartenes",
    banners: [
      {
        id: 1,
        alt_text: "Set de sartenes",
        order_index: 0,
        variants: [{ width: 480, format: "webp", url: "https://r2.example/1/480.webp" }],
        top_edge_color: null,
        bottom_edge_color: null,
      },
    ],
    cta_positions: [1],
    cta_backgrounds: [],
    form_presentation: "inline",
    ...overrides,
  };
}

async function openForm(landing: PublicLanding = makeLanding()) {
  vi.mocked(publicApi.getLanding).mockResolvedValue(landing);
  render(
    <MemoryRouter initialEntries={[`/p/${landing.slug}`]}>
      <Routes>
        <Route path="/p/:slug" element={<LandingPage />} />
      </Routes>
    </MemoryRouter>,
  );
  const user = userEvent.setup();
  const cta = (await screen.findAllByRole("button", { name: /Pedir ahora/i }))[0];
  await user.click(cta);
  return user;
}

async function fillRequiredFields(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Nombre completo"), "Ana Gómez");
  await user.type(screen.getByLabelText(/Número de celular/), "3001234567");
  await user.type(screen.getByLabelText("Departamento"), "Antioquia");
  await user.type(screen.getByLabelText("Ciudad o municipio"), "Medellín");
  await user.type(screen.getByLabelText("Dirección de entrega"), "Calle 10 # 43-25");
}

describe("Dirección 2 (frontend-only)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(publicApi.createOrder).mockResolvedValue({ order_id: 1, status: "pending" });
  });

  it("renders the field right after the address field", async () => {
    await openForm();

    expect(screen.getByLabelText("Dirección de entrega")).toBeInTheDocument();
    expect(screen.getByLabelText("Dirección 2 (opcional)")).toBeInTheDocument();
  });

  it("joins address and Dirección 2 with a space in the submitted request", async () => {
    const user = await openForm();
    await fillRequiredFields(user);
    await user.type(screen.getByLabelText("Dirección 2 (opcional)"), "Torre 3, apto 302");

    await user.click(screen.getByRole("button", { name: /Confirmar pedido/ }));

    await waitFor(() => expect(publicApi.createOrder).toHaveBeenCalled());
    const payload = vi.mocked(publicApi.createOrder).mock.calls[0][0];
    expect(payload.address).toBe("Calle 10 # 43-25 Torre 3, apto 302");
    // Never sent as its own field: the backend contract is untouched.
    expect(payload).not.toHaveProperty("address2");
  });

  it("submits only the trimmed address when Dirección 2 is left blank", async () => {
    const user = await openForm();
    await fillRequiredFields(user);

    await user.click(screen.getByRole("button", { name: /Confirmar pedido/ }));

    await waitFor(() => expect(publicApi.createOrder).toHaveBeenCalled());
    const payload = vi.mocked(publicApi.createOrder).mock.calls[0][0];
    expect(payload.address).toBe("Calle 10 # 43-25");
  });

  it("does not require Dirección 2 to submit the form", async () => {
    const user = await openForm();
    // The optional field carries no `required` attribute, unlike address.
    expect(screen.getByLabelText("Dirección 2 (opcional)")).not.toBeRequired();
    expect(screen.getByLabelText("Dirección de entrega")).toBeRequired();

    await fillRequiredFields(user);
    await user.click(screen.getByRole("button", { name: /Confirmar pedido/ }));

    await waitFor(() => expect(publicApi.createOrder).toHaveBeenCalledTimes(1));
  });
});
