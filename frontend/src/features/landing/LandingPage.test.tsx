import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LandingPage } from "./LandingPage";
import { ApiError, publicApi } from "../../api";
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

const SAMPLE_LANDING: PublicLanding = {
  landing_id: 1,
  product_id: 1,
  product_name: "Audífonos Bluetooth",
  product_sku: "AUD-001",
  product_price: 89900,
  slug: "audifonos-bluetooth",
  banners: [
    {
      id: 1,
      alt_text: "Audífonos Bluetooth vista frontal",
      order_index: 0,
      variants: [{ width: 480, height: 288, format: "webp", url: "https://r2.example/1/480.webp" }],
      top_edge_color: null,
      bottom_edge_color: "#1a2b3c",
    },
    {
      id: 2,
      alt_text: "Audífonos Bluetooth en uso",
      order_index: 1,
      variants: [{ width: 480, height: 288, format: "webp", url: "https://r2.example/2/480.webp" }],
      top_edge_color: "#3c2b1a",
      bottom_edge_color: null,
    },
  ],
  cta_positions: [1],
  cta_backgrounds: [
    {
      position: 1,
      top_color: "#1a2b3c",
      bottom_color: "#3c2b1a",
      blend_color: "#2b2b2b",
      foreground: "light",
      source: "blend",
    },
  ],
  form_presentation: "inline",
};

function renderAtSlug(slug: string) {
  return render(
    <MemoryRouter initialEntries={[`/p/${slug}`]}>
      <Routes>
        <Route path="/p/:slug" element={<LandingPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("LandingPage", () => {
  beforeEach(() => {
    window.dataLayer = [];
    vi.mocked(publicApi.getLanding).mockResolvedValue(SAMPLE_LANDING);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders banners and the CTA at the configured position, then records a view", async () => {
    renderAtSlug("audifonos-bluetooth");

    expect(await screen.findByAltText("Audífonos Bluetooth vista frontal")).toBeInTheDocument();
    expect(screen.getByAltText("Audífonos Bluetooth en uso")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Pedir ahora/i })[0]).toBeInTheDocument();

    await waitFor(() =>
      expect(publicApi.recordView).toHaveBeenCalledWith("audifonos-bluetooth"),
    );
  });

  it("opens the COD form as a pop-up and records a CTA click on activation", async () => {
    const user = userEvent.setup();
    renderAtSlug("audifonos-bluetooth");

    await screen.findAllByRole("button", { name: /Pedir ahora/i });
    expect(screen.queryByLabelText("Nombre")).not.toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: /Pedir ahora/i })[0]);

    expect(publicApi.recordCtaClick).toHaveBeenCalledWith("audifonos-bluetooth");
    expect(window.dataLayer).toContainEqual(
      expect.objectContaining({ event: "begin_checkout" }),
    );
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByLabelText("Nombre")).toBeInTheDocument();
    expect(screen.getByLabelText("Apellido")).toBeInTheDocument();
  });

  it("never renders the COD form until the CTA is activated, whatever form_presentation says", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue({
      ...SAMPLE_LANDING,
      form_presentation: "inline",
    });
    const user = userEvent.setup();
    renderAtSlug("audifonos-bluetooth");

    await screen.findAllByRole("button", { name: /Pedir ahora/i });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: /Pedir ahora/i })[0]);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByLabelText("Nombre")).toBeInTheDocument();
  });

  it("restates the offer and the total inside the pop-up", async () => {
    const user = userEvent.setup();
    renderAtSlug("audifonos-bluetooth");

    await user.click((await screen.findAllByRole("button", { name: /Pedir ahora/i }))[0]);

    const dialog = screen.getByRole("dialog");
    // The offer is restated as the priced quantity tiers plus the total on the
    // confirm button. The product name and the COD promise are not repeated
    // here: the sheet's own title/subtitle and the note under the button
    // already carry them.
    expect(dialog).toHaveTextContent("1 unidad");
    expect(dialog).toHaveTextContent(/Pago seguro contraentrega/i);
    expect(screen.getByRole("button", { name: /Confirmar pedido/i })).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: /2 unidades/ }));
    expect(dialog).toHaveTextContent("2 unidades");
  });

  it("closes the pop-up on Escape and returns focus to the CTA that opened it", async () => {
    const user = userEvent.setup();
    renderAtSlug("audifonos-bluetooth");

    const cta = (await screen.findAllByRole("button", { name: /Pedir ahora/i }))[0];
    await user.click(cta);
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(cta).toHaveFocus();
  });

  it("blocks submission with a field-level message instead of calling the API", async () => {
    const user = userEvent.setup();
    renderAtSlug("audifonos-bluetooth");

    await user.click((await screen.findAllByRole("button", { name: /Pedir ahora/i }))[0]);
    await user.click(screen.getByRole("button", { name: /Confirmar pedido/i }));

    expect(await screen.findByText("Escribe tu nombre.")).toBeInTheDocument();
    expect(publicApi.createOrder).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Nombre")).toHaveFocus();
  });

  it("submits the COD form and shows the confirmation state", async () => {
    vi.mocked(publicApi.createOrder).mockResolvedValue({
      order_id: 42,
      status: "pending",
      total_price: 89900,
    });
    const user = userEvent.setup();
    renderAtSlug("audifonos-bluetooth");

    await user.click((await screen.findAllByRole("button", { name: /Pedir ahora/i }))[0]);
    await user.type(screen.getByLabelText("Nombre"), "María");
    await user.type(screen.getByLabelText("Apellido"), "Gómez");
    await user.type(screen.getByLabelText("Celular / WhatsApp"), "3001234567");
    await user.selectOptions(screen.getByLabelText("Departamento"), "ANTIOQUIA");
    await user.selectOptions(screen.getByLabelText("Ciudad o municipio"), "MEDELLÍN");
    await user.type(screen.getByLabelText("Dirección de entrega"), "Calle 10 #20-30");
    await user.click(screen.getByRole("button", { name: /Confirmar pedido/i }));

    expect(await screen.findByText("¡Pedido recibido!")).toBeInTheDocument();
    expect(publicApi.createOrder).toHaveBeenCalledWith(
      expect.objectContaining({ landing_slug: "audifonos-bluetooth", full_name: "María Gómez" }),
    );
    expect(window.dataLayer).toContainEqual({
      event: "purchase",
      ecommerce: expect.objectContaining({
        transaction_id: "42",
        currency: "COP",
        value: 89900,
      }),
      user_data: expect.objectContaining({
        phone: "+573001234567",
        first_name: "María",
        last_name: "Gómez",
      }),
    });
  });

  it("does not report a fraud-flagged submission as a Meta purchase", async () => {
    vi.mocked(publicApi.createOrder).mockResolvedValue({
      order_id: 43,
      status: "flagged_fraud",
      total_price: 89900,
    });
    const user = userEvent.setup();
    renderAtSlug("audifonos-bluetooth");

    await user.click((await screen.findAllByRole("button", { name: /Pedir ahora/i }))[0]);
    await user.type(screen.getByLabelText("Nombre"), "María");
    await user.type(screen.getByLabelText("Apellido"), "Gómez");
    await user.type(screen.getByLabelText("Celular / WhatsApp"), "3001234567");
    await user.selectOptions(screen.getByLabelText("Departamento"), "ANTIOQUIA");
    await user.selectOptions(screen.getByLabelText("Ciudad o municipio"), "MEDELLÍN");
    await user.type(screen.getByLabelText("Dirección de entrega"), "Calle 10 #20-30");
    await user.click(screen.getByRole("button", { name: /Confirmar pedido/i }));

    expect(await screen.findByText("¡Pedido recibido!")).toBeInTheDocument();
    expect(window.dataLayer?.some((entry) => entry.event === "purchase")).toBe(false);
  });

  it("maps a 422 field error from the backend onto the corresponding control", async () => {
    vi.mocked(publicApi.createOrder).mockRejectedValue(
      new ApiError(422, "Invalid Colombian phone number.", { phone: "Invalid Colombian phone number." }),
    );
    const user = userEvent.setup();
    renderAtSlug("audifonos-bluetooth");

    await user.click((await screen.findAllByRole("button", { name: /Pedir ahora/i }))[0]);
    await user.type(screen.getByLabelText("Nombre"), "María");
    await user.type(screen.getByLabelText("Apellido"), "Gómez");
    await user.type(screen.getByLabelText("Celular / WhatsApp"), "3009999999");
    await user.selectOptions(screen.getByLabelText("Departamento"), "ANTIOQUIA");
    await user.selectOptions(screen.getByLabelText("Ciudad o municipio"), "MEDELLÍN");
    await user.type(screen.getByLabelText("Dirección de entrega"), "Calle 10 #20-30");
    await user.click(screen.getByRole("button", { name: /Confirmar pedido/i }));

    expect(await screen.findByText("Invalid Colombian phone number.")).toBeInTheDocument();
  });

  it("renders the not-found page for an unknown slug (no information disclosure)", async () => {
    vi.mocked(publicApi.getLanding).mockRejectedValue(new ApiError(404, "Landing not found"));
    renderAtSlug("no-existe");

    expect(await screen.findByText("Página no encontrada")).toBeInTheDocument();
  });
});
