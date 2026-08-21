/**
 * Tests for split COD form controls. Joined values preserve the existing local
 * order fields while exact parts are also sent for fulfillment synchronization.
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
      getLocations: vi.fn().mockResolvedValue({ departments: [{ code: "05", name: "ANTIOQUIA", cities: [{ code: "05001", name: "MEDELLÍN" }] }] }),
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
        variants: [{ width: 480, height: 288, format: "webp", url: "https://r2.example/1/480.webp" }],
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
  await user.type(screen.getByLabelText("Nombre"), "Ana");
  await user.type(screen.getByLabelText("Apellido"), "Gómez");
  await user.type(screen.getByLabelText(/Número de celular/), "3001234567");
  await user.selectOptions(screen.getByLabelText("Departamento"), "ANTIOQUIA");
  await user.selectOptions(screen.getByLabelText("Ciudad o municipio"), "MEDELLÍN");
  await user.type(screen.getByLabelText("Dirección de entrega"), "Calle 10 # 43-25");
}

describe("COD form frontend-only fields", () => {
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
    expect(payload.address1).toBe("Calle 10 # 43-25");
    expect(payload.address2).toBe("Torre 3, apto 302");
    expect(payload.variant_selections).toEqual([]);
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

  it("requires separate first-name and last-name controls", async () => {
    await openForm();

    expect(screen.getByLabelText("Nombre")).toBeRequired();
    expect(screen.getByLabelText("Apellido")).toBeRequired();
    expect(screen.queryByLabelText("Nombre completo")).not.toBeInTheDocument();
  });

  it("joins the trimmed name parts and also preserves the exact fulfillment parts", async () => {
    const user = await openForm();
    await user.type(screen.getByLabelText("Nombre"), "  Ana María  ");
    await user.type(screen.getByLabelText("Apellido"), "  Gómez Ruiz  ");
    await user.type(screen.getByLabelText(/Número de celular/), "3001234567");
    await user.selectOptions(screen.getByLabelText("Departamento"), "ANTIOQUIA");
    await user.selectOptions(screen.getByLabelText("Ciudad o municipio"), "MEDELLÍN");
    await user.type(screen.getByLabelText("Dirección de entrega"), "Calle 10 # 43-25");

    await user.click(screen.getByRole("button", { name: /Confirmar pedido/ }));

    await waitFor(() => expect(publicApi.createOrder).toHaveBeenCalledTimes(1));
    const payload = vi.mocked(publicApi.createOrder).mock.calls[0][0];
    expect(payload.full_name).toBe("Ana María Gómez Ruiz");
    expect(payload.first_name).toBe("Ana María");
    expect(payload.last_name).toBe("Gómez Ruiz");
  });

  it("blocks submission when the last name is missing and focuses it", async () => {
    const user = await openForm();
    await user.type(screen.getByLabelText("Nombre"), "Ana");

    await user.click(screen.getByRole("button", { name: /Confirmar pedido/ }));

    expect(await screen.findByText("Escribe tu apellido.")).toBeInTheDocument();
    expect(screen.getByLabelText("Apellido")).toHaveFocus();
    expect(publicApi.createOrder).not.toHaveBeenCalled();
  });

  it("uses the configured default offer and submits options for every unit", async () => {
    const user = await openForm(
      makeLanding({
        default_offer_quantity: 2,
        variant_options: [
          { name: "Color", values: ["Gris", "Negro"] },
          { name: "Talla", values: ["M", "L"] },
        ],
      }),
    );

    expect(screen.getByRole("radio", { name: /2 unidades/ })).toBeChecked();
    expect(screen.getByLabelText("Color, unidad 1")).toHaveValue("Gris");
    await user.selectOptions(screen.getByLabelText("Color, unidad 2"), "Negro");
    await user.selectOptions(screen.getByLabelText("Talla, unidad 2"), "L");
    await fillRequiredFields(user);
    await user.click(screen.getByRole("button", { name: /Confirmar pedido/ }));

    await waitFor(() => expect(publicApi.createOrder).toHaveBeenCalledTimes(1));
    expect(vi.mocked(publicApi.createOrder).mock.calls[0][0].variant_selections).toEqual([
      { Color: "Gris", Talla: "M" },
      { Color: "Negro", Talla: "L" },
    ]);
  });
});
