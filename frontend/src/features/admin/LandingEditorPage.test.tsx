import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LandingEditorPage } from "./LandingEditorPage";
import { ApiError, landingsApi } from "../../api";
import type { LandingBanner, LandingDetail } from "../../api";

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...actual,
    landingsApi: {
      get: vi.fn(),
      updateConfig: vi.fn(),
      uploadBanner: vi.fn(),
      updateBanner: vi.fn(),
      reorderBanners: vi.fn(),
      deleteBanner: vi.fn(),
      publish: vi.fn(),
      unpublish: vi.fn(),
      // The editor mounts the conversion components panel, which reads its own
      // list on mount; an empty list keeps these tests about the editor.
      listBlocks: vi
        .fn()
        .mockResolvedValue({ blocks: [], slots: ["0-1 · antes de banner 1"], allowed_block_types: [] }),
      createBlock: vi.fn(),
      updateBlock: vi.fn(),
      deleteBlock: vi.fn(),
    },
  };
});

function banner(id: number, orderIndex: number, altText: string): LandingBanner {
  return {
    id,
    alt_text: altText,
    order_index: orderIndex,
    image_asset_id: id * 10,
    image_status: "complete",
    variants: [
      {
        width: 480,
        height: 320,
        format: "jpeg",
        url: `https://images.example.com/variants/key-${id}/480.jpg`,
      },
    ],
  };
}

const DETAIL: LandingDetail = {
  id: 7,
  product_id: 3,
  product_name: "Audífonos inalámbricos",
  product_sku: "AUD-001",
  product_status: "active",
  slug: "audifonos-inalambricos",
  status: "draft",
  cta_mode: "after_every",
  cta_interval: null,
  cta_positions: [],
  form_presentation: "inline",
  cta_band_style: "gradient",
  accent_color: "#1a7a4c",
  form_accent_color: null,
  offer_count: 3,
  default_offer_quantity: 1,
  offers: [
    { quantity: 1, label: "1 unidad", sublabel: null, discount_percent: 0, compare_at_price: null },
    { quantity: 2, label: "2 unidades", sublabel: null, discount_percent: 0, compare_at_price: null },
    { quantity: 3, label: "3 unidades", sublabel: null, discount_percent: 0, compare_at_price: null },
  ],
  banner_count: 2,
  cta_text: null,
  cta_animation: null,
  cta_text_overrides: {},
  blocks_dark_mode: false,
  banners: [banner(1, 0, "Primero"), banner(2, 1, "Segundo")],
  resolved_cta_positions: [1, 2],
};

function renderEditor() {
  return render(
    <MemoryRouter initialEntries={["/admin/landings/7"]}>
      <Routes>
        <Route path="/admin/landings/:landingId" element={<LandingEditorPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("LandingEditorPage", () => {
  beforeEach(() => {
    vi.mocked(landingsApi.get).mockResolvedValue(DETAIL);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the banner sequence with previews and alt-text controls", async () => {
    renderEditor();

    expect(await screen.findByText("Banners (2/15)")).toBeInTheDocument();
    const altInputs = screen.getAllByLabelText("Texto alternativo");
    expect(altInputs[0]).toHaveValue("Primero");
    expect(screen.getByAltText("Primero")).toHaveAttribute(
      "src",
      "https://images.example.com/variants/key-1/480.jpg",
    );
  });

  it("moves a banner down through the ordering control", async () => {
    const user = userEvent.setup();
    vi.mocked(landingsApi.updateBanner).mockResolvedValue({
      banners: [banner(2, 0, "Segundo"), banner(1, 1, "Primero")],
    });
    renderEditor();
    await screen.findByText("Banners (2/15)");

    await user.click(screen.getByRole("button", { name: "Bajar banner 1" }));

    await waitFor(() =>
      expect(landingsApi.updateBanner).toHaveBeenCalledWith(7, 1, { order_index: 1 }),
    );
  });

  it("disables moving the first banner up and the last banner down", async () => {
    renderEditor();
    await screen.findByText("Banners (2/15)");

    expect(screen.getByRole("button", { name: "Subir banner 1" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Bajar banner 2" })).toBeDisabled();
  });

  it("requires confirmation before deleting a banner", async () => {
    const user = userEvent.setup();
    vi.mocked(landingsApi.deleteBanner).mockResolvedValue({
      banners: [banner(2, 0, "Segundo")],
    });
    renderEditor();
    await screen.findByText("Banners (2/15)");

    await user.click(screen.getAllByRole("button", { name: "Eliminar" })[0]);
    expect(landingsApi.deleteBanner).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Confirmar" }));
    await waitFor(() => expect(landingsApi.deleteBanner).toHaveBeenCalledWith(7, 1));
  });

  it("uploads a banner with its alternative text", async () => {
    const user = userEvent.setup();
    vi.mocked(landingsApi.uploadBanner).mockResolvedValue(banner(3, 2, "Tercero"));
    renderEditor();
    await screen.findByText("Banners (2/15)");

    const file = new File(["binary"], "banner.jpg", { type: "image/jpeg" });
    await user.upload(screen.getByLabelText(/^Imagen/), file);
    await user.type(screen.getByLabelText(/^Texto alternativo \(1-200/), "Tercero");
    await user.click(screen.getByRole("button", { name: "Subir banner" }));

    await waitFor(() => expect(landingsApi.uploadBanner).toHaveBeenCalledWith(7, file, "Tercero"));
  });

  it("binds a rejected slug to its control and exposes it to assistive tech", async () => {
    const user = userEvent.setup();
    vi.mocked(landingsApi.updateConfig).mockRejectedValue(
      new ApiError(422, "Slug inválido", { slug: "Slug inválido" }),
    );
    renderEditor();
    await screen.findByText("Banners (2/15)");

    await user.click(screen.getByRole("button", { name: "Guardar configuración" }));

    const slugInput = await screen.findByLabelText("Slug público");
    await waitFor(() => expect(slugInput).toHaveAttribute("aria-invalid", "true"));
    expect(slugInput).toHaveAccessibleDescription("Slug inválido");
  });

  it("shows the CTA interval control only for the every_n mode", async () => {
    const user = userEvent.setup();
    renderEditor();
    await screen.findByText("Banners (2/15)");

    expect(screen.queryByLabelText("Intervalo (1-15)")).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Ubicación de los CTA"), "every_n");
    expect(screen.getByLabelText("Intervalo (1-15)")).toBeInTheDocument();
  });

  it("saves the CTA configuration, band style, and form presentation", async () => {
    const user = userEvent.setup();
    vi.mocked(landingsApi.updateConfig).mockResolvedValue({
      ...DETAIL,
      cta_mode: "every_n",
      cta_interval: 2,
      form_presentation: "modal",
      cta_band_style: "solid",
    });
    renderEditor();
    await screen.findByText("Banners (2/15)");

    await user.selectOptions(screen.getByLabelText("Ubicación de los CTA"), "every_n");
    await user.clear(screen.getByLabelText("Intervalo (1-15)"));
    await user.type(screen.getByLabelText("Intervalo (1-15)"), "2");
    await user.selectOptions(screen.getByLabelText("Formulario COD"), "modal");
    await user.selectOptions(screen.getByLabelText("Fondo del botón CTA"), "solid");
    await user.selectOptions(screen.getByLabelText("Oferta preseleccionada"), "2");
    await user.click(screen.getByRole("button", { name: "Guardar configuración" }));

    await waitFor(() =>
      expect(landingsApi.updateConfig).toHaveBeenCalledWith(7, {
        slug: "audifonos-inalambricos",
        cta_mode: "every_n",
        cta_interval: 2,
        cta_positions: [],
        form_presentation: "modal",
        cta_band_style: "solid",
        accent_color: "#1a7a4c",
        form_accent_color: "",
        blocks_accent_color: "",
        offer_count: 3,
        default_offer_quantity: 2,
        cta_text: null,
        cta_animation: null,
        cta_text_overrides: {},
        cta_color_modes: {},
        blocks_dark_mode: false,
        offers: [
          {
            quantity: 1,
            label: "1 unidad",
            sublabel: "",
            discount_percent: null,
            discount_amount: null,
            compare_at_price: null,
          },
          {
            quantity: 2,
            label: "2 unidades",
            sublabel: "",
            discount_percent: null,
            discount_amount: null,
            compare_at_price: null,
          },
          {
            quantity: 3,
            label: "3 unidades",
            sublabel: "",
            discount_percent: null,
            discount_amount: null,
            compare_at_price: null,
          },
        ],
      }),
    );
  });

  it("reflects the stored band style and its saved value in the control", async () => {
    const user = userEvent.setup();
    vi.mocked(landingsApi.get).mockResolvedValue({ ...DETAIL, cta_band_style: "solid" });
    vi.mocked(landingsApi.updateConfig).mockResolvedValue({ ...DETAIL, cta_band_style: "solid" });
    renderEditor();
    await screen.findByText("Banners (2/15)");

    const control = screen.getByLabelText("Fondo del botón CTA") as HTMLSelectElement;
    expect(control.value).toBe("solid");

    await user.selectOptions(control, "gradient");
    await user.click(screen.getByRole("button", { name: "Guardar configuración" }));

    await waitFor(() =>
      expect(landingsApi.updateConfig).toHaveBeenCalledWith(
        7,
        expect.objectContaining({ cta_band_style: "gradient" }),
      ),
    );
  });

  it("binds a rejected band style to its own control", async () => {
    const user = userEvent.setup();
    vi.mocked(landingsApi.updateConfig).mockRejectedValue(
      new ApiError(422, "No se pudo guardar.", {
        cta_band_style: "El fondo debe ser degradado o plano.",
      }),
    );
    renderEditor();
    await screen.findByText("Banners (2/15)");

    await user.click(screen.getByRole("button", { name: "Guardar configuración" }));

    const control = await screen.findByLabelText("Fondo del botón CTA");
    // The error joins the standing hint rather than replacing it, so the
    // explanation of what the control does survives the failure.
    await waitFor(() =>
      expect(control).toHaveAttribute(
        "aria-describedby",
        "landing-cta-band-style-error landing-cta-band-style-hint",
      ),
    );
    const message = document.getElementById("landing-cta-band-style-error");
    expect(message).toHaveAttribute("role", "alert");
    expect(message).toHaveTextContent("El fondo debe ser degradado o plano.");
  });

  it("publishes a draft landing and reflects the stored status", async () => {
    const user = userEvent.setup();
    vi.mocked(landingsApi.publish).mockResolvedValue({ ...DETAIL, status: "published" });
    renderEditor();
    await screen.findByText("Banners (2/15)");

    await user.click(screen.getByRole("button", { name: "Publicar" }));

    await waitFor(() => expect(landingsApi.publish).toHaveBeenCalledWith(7));
    expect(await screen.findByRole("button", { name: "Despublicar" })).toBeInTheDocument();
  });

  it("surfaces publish gating rejection without showing a published status", async () => {
    const user = userEvent.setup();
    vi.mocked(landingsApi.get).mockResolvedValue({
      ...DETAIL,
      banners: [],
      banner_count: 0,
      resolved_cta_positions: [],
    });
    vi.mocked(landingsApi.publish).mockRejectedValue(
      new ApiError(422, "A landing must have between 1 and 15 banners to publish.", {
        banners: "A landing must have between 1 and 15 banners to publish.",
      }),
    );
    renderEditor();
    await screen.findByText("Banners (0/15)");

    await user.click(screen.getByRole("button", { name: "Publicar" }));

    await waitFor(() =>
      expect(screen.getAllByRole("alert")[0]).toHaveTextContent(
        "A landing must have between 1 and 15 banners to publish.",
      ),
    );
    expect(screen.getByRole("button", { name: "Publicar" })).toBeInTheDocument();
    expect(screen.queryByText("Publicado")).not.toBeInTheDocument();
  });
});

/**
 * The offer and accent controls. What matters here is that the merchant can only
 * express configurations the public form can actually render: the number of
 * offer rows follows the count, a single unit is offered a reference price
 * instead of a discount, and a blank sub-text is submitted as the "no second
 * line" value rather than being dropped.
 */
describe("LandingEditorPage offers and accent", () => {
  beforeEach(() => {
    vi.mocked(landingsApi.get).mockResolvedValue(DETAIL);
    vi.mocked(landingsApi.updateConfig).mockResolvedValue(DETAIL);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders one editable offer per configured offer", async () => {
    renderEditor();
    await screen.findByText("Banners (2/15)");

    expect(screen.getByLabelText("Número de ofertas")).toHaveValue("3");
    // Three offers configured -> three sets of copy fields.
    expect(screen.getByLabelText("Texto", { selector: "#landing-offer-label-1" })).toHaveValue(
      "1 unidad",
    );
    expect(screen.getByLabelText("Texto", { selector: "#landing-offer-label-3" })).toHaveValue(
      "3 unidades",
    );
  });

  it("shows fewer offer rows when the count is lowered", async () => {
    const user = userEvent.setup();
    renderEditor();
    await screen.findByText("Banners (2/15)");

    await user.selectOptions(screen.getByLabelText("Número de ofertas"), "1");

    expect(
      screen.getByLabelText("Texto", { selector: "#landing-offer-label-1" }),
    ).toBeInTheDocument();
    // The merchant never edits copy for an offer the buyer will not see.
    expect(document.querySelector("#landing-offer-label-2")).toBeNull();
    expect(document.querySelector("#landing-offer-label-3")).toBeNull();
  });

  it("offers a reference price on one unit and a discount on the rest", async () => {
    renderEditor();
    await screen.findByText("Banners (2/15)");

    // One unit has no volume saving to express, so it gets the anchor price.
    expect(document.querySelector("#landing-offer-compare-1")).not.toBeNull();
    expect(document.querySelector("#landing-offer-discount-1")).toBeNull();
    // Multi-unit offers get a real percentage off instead.
    expect(document.querySelector("#landing-offer-discount-2")).not.toBeNull();
    expect(document.querySelector("#landing-offer-compare-2")).toBeNull();
  });

  it("caps the discount input at the maximum the backend accepts", async () => {
    renderEditor();
    await screen.findByText("Banners (2/15)");

    const discount = document.querySelector("#landing-offer-discount-2");
    expect(discount).toHaveAttribute("max", "90");
  });

  it("submits the edited copy, discount, and accent color", async () => {
    const user = userEvent.setup();
    renderEditor();
    await screen.findByText("Banners (2/15)");

    await user.clear(screen.getByLabelText("Texto", { selector: "#landing-offer-label-2" }));
    await user.type(
      screen.getByLabelText("Texto", { selector: "#landing-offer-label-2" }),
      "Llévate dos",
    );
    await user.type(
      screen.getByLabelText("Sub-texto (opcional)", { selector: "#landing-offer-sublabel-2" }),
      "Ahorra 10%",
    );
    await user.type(document.querySelector("#landing-offer-discount-2")!, "10");
    await user.clear(screen.getByLabelText("Color de la landing en hexadecimal"));
    await user.type(screen.getByLabelText("Color de la landing en hexadecimal"), "#2563eb");
    await user.click(screen.getByRole("button", { name: "Guardar configuración" }));

    await waitFor(() => expect(landingsApi.updateConfig).toHaveBeenCalled());
    const payload = vi.mocked(landingsApi.updateConfig).mock.calls[0][1];
    expect(payload.accent_color).toBe("#2563eb");
    expect(payload.offer_count).toBe(3);
    expect(payload.offers?.[1]).toEqual({
      quantity: 2,
      label: "Llévate dos",
      sublabel: "Ahorra 10%",
      discount_percent: 10,
      discount_amount: null,
      compare_at_price: null,
    });
  });

  it("submits a fixed COP discount and clears the percentage", async () => {
    const user = userEvent.setup();
    renderEditor();
    await screen.findByText("Banners (2/15)");

    await user.type(document.querySelector("#landing-offer-discount-2")!, "10");
    await user.type(document.querySelector("#landing-offer-discount-amount-2")!, "20000");
    await user.click(screen.getByRole("button", { name: "Guardar configuración" }));

    await waitFor(() => expect(landingsApi.updateConfig).toHaveBeenCalled());
    const offer = vi.mocked(landingsApi.updateConfig).mock.calls[0][1].offers?.[1];
    expect(offer?.discount_percent).toBeNull();
    expect(offer?.discount_amount).toBe(20000);
  });

  it("submits a blank sub-text as the value that turns the second line off", async () => {
    const user = userEvent.setup();
    renderEditor();
    await screen.findByText("Banners (2/15)");

    await user.click(screen.getByRole("button", { name: "Guardar configuración" }));

    await waitFor(() => expect(landingsApi.updateConfig).toHaveBeenCalled());
    const payload = vi.mocked(landingsApi.updateConfig).mock.calls[0][1];
    // Empty string is meaningful — not omitted, not null.
    expect(payload.offers?.[0].sublabel).toBe("");
    // An untouched discount is cleared rather than sent as 0, so the backend
    // applies its own default.
    expect(payload.offers?.[0].discount_percent).toBeNull();
  });

  it("binds a backend offer error to the offers fieldset", async () => {
    const user = userEvent.setup();
    vi.mocked(landingsApi.updateConfig).mockRejectedValue(
      new ApiError(422, "Offer 2: offer text is required.", {
        offers: "Offer 2: offer text is required.",
      }),
    );
    renderEditor();
    await screen.findByText("Banners (2/15)");

    await user.click(screen.getByRole("button", { name: "Guardar configuración" }));

    // Every offer's text input points at the message, so assistive tech reads
    // the reason alongside the control that produced it (Requirement 8.19).
    await waitFor(() =>
      expect(
        screen.getByLabelText("Texto", { selector: "#landing-offer-label-2" }),
      ).toHaveAccessibleDescription("Offer 2: offer text is required."),
    );
    const announced = document.querySelector("#landing-offers-error");
    expect(announced).toHaveAttribute("role", "alert");
    expect(announced).toHaveTextContent("Offer 2: offer text is required.");
  });

  it("binds a backend accent error to the accent control", async () => {
    const user = userEvent.setup();
    vi.mocked(landingsApi.updateConfig).mockRejectedValue(
      new ApiError(422, "Accent color must be a hex color such as #1a7a4c.", {
        accent_color: "Accent color must be a hex color such as #1a7a4c.",
      }),
    );
    renderEditor();
    await screen.findByText("Banners (2/15)");

    await user.click(screen.getByRole("button", { name: "Guardar configuración" }));

    const swatch = await screen.findByLabelText("Color de la landing");
    await waitFor(() => expect(swatch).toHaveAttribute("aria-invalid", "true"));
    expect(swatch).toHaveAccessibleDescription(
      /Accent color must be a hex color such as #1a7a4c\./,
    );
  });
});

/**
 * The form accent color (separate from the CTA/page accent) and the
 * per-CTA-position text override. What matters here is that the two remain
 * independent controls that submit independently, and that the override list
 * only ever offers the CTA positions the current banner sequence actually
 * resolves to.
 */
describe("LandingEditorPage form accent and per-CTA text override", () => {
  beforeEach(() => {
    vi.mocked(landingsApi.get).mockResolvedValue(DETAIL);
    vi.mocked(landingsApi.updateConfig).mockResolvedValue(DETAIL);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("submits a blank form accent color as an explicit reset", async () => {
    const user = userEvent.setup();
    renderEditor();
    await screen.findByText("Banners (2/15)");

    await user.click(screen.getByRole("button", { name: "Guardar configuración" }));

    await waitFor(() => expect(landingsApi.updateConfig).toHaveBeenCalled());
    const payload = vi.mocked(landingsApi.updateConfig).mock.calls[0][1];
    expect(payload.form_accent_color).toBe("");
  });

  it("submits a custom form accent color independently of the CTA accent", async () => {
    const user = userEvent.setup();
    renderEditor();
    await screen.findByText("Banners (2/15)");

    await user.type(
      screen.getByLabelText("Color del formulario en hexadecimal"),
      "#e11d48",
    );
    await user.click(screen.getByRole("button", { name: "Guardar configuración" }));

    await waitFor(() => expect(landingsApi.updateConfig).toHaveBeenCalled());
    const payload = vi.mocked(landingsApi.updateConfig).mock.calls[0][1];
    expect(payload.form_accent_color).toBe("#e11d48");
    expect(payload.accent_color).toBe("#1a7a4c");
  });

  it("uses the form accent by default and submits an independent block color", async () => {
    const user = userEvent.setup();
    renderEditor();
    await screen.findByText("Banners (2/15)");

    const input = screen.getByLabelText("Color de componentes en hexadecimal");
    expect(input).toHaveValue("");
    await user.type(input, "#7c3aed");
    await user.click(screen.getByRole("button", { name: "Guardar configuración" }));

    await waitFor(() => expect(landingsApi.updateConfig).toHaveBeenCalled());
    const payload = vi.mocked(landingsApi.updateConfig).mock.calls[0][1];
    expect(payload.blocks_accent_color).toBe("#7c3aed");
    expect(payload.form_accent_color).toBe("");
  });

  it("clears saved form and component colors through their inheritance buttons", async () => {
    const user = userEvent.setup();
    vi.mocked(landingsApi.get).mockResolvedValue({
      ...DETAIL,
      form_accent_color: "#e11d48",
      blocks_accent_color: "#7c3aed",
    });
    renderEditor();
    await screen.findByText("Banners (2/15)");

    await user.click(screen.getByRole("button", { name: "Usar el color de la landing" }));
    await user.click(screen.getByRole("button", { name: "Usar el color del formulario" }));
    await user.click(screen.getByRole("button", { name: "Guardar configuración" }));

    await waitFor(() => expect(landingsApi.updateConfig).toHaveBeenCalled());
    const payload = vi.mocked(landingsApi.updateConfig).mock.calls[0][1];
    expect(payload.form_accent_color).toBe("");
    expect(payload.blocks_accent_color).toBe("");
  });

  it("binds a backend form accent error to its own control", async () => {
    const user = userEvent.setup();
    vi.mocked(landingsApi.updateConfig).mockRejectedValue(
      new ApiError(422, "Accent color must be a hex color such as #1a7a4c.", {
        form_accent_color: "Accent color must be a hex color such as #1a7a4c.",
      }),
    );
    renderEditor();
    await screen.findByText("Banners (2/15)");

    await user.click(screen.getByRole("button", { name: "Guardar configuración" }));

    const swatch = await screen.findByLabelText("Color del formulario");
    await waitFor(() => expect(swatch).toHaveAttribute("aria-invalid", "true"));
    expect(swatch).toHaveAccessibleDescription(
      /Accent color must be a hex color such as #1a7a4c\./,
    );
  });

  it("offers one override row per resolved CTA position", async () => {
    renderEditor();
    await screen.findByText("Banners (2/15)");

    expect(screen.getByLabelText("CTA #1")).toBeInTheDocument();
    expect(screen.getByLabelText("CTA #2")).toBeInTheDocument();
    expect(screen.queryByLabelText("CTA #3")).not.toBeInTheDocument();
  });

  it("does not render the override list when there are no resolved CTA positions", async () => {
    vi.mocked(landingsApi.get).mockResolvedValue({ ...DETAIL, resolved_cta_positions: [] });
    renderEditor();
    await screen.findByText("Banners (2/15)");

    expect(screen.queryByText("Texto por CTA (opcional)")).not.toBeInTheDocument();
  });

  it("submits an override only for the position it was typed into", async () => {
    const user = userEvent.setup();
    renderEditor();
    await screen.findByText("Banners (2/15)");

    await user.type(screen.getByLabelText("CTA #2"), "Lo quiero ahora");
    await user.click(screen.getByRole("button", { name: "Guardar configuración" }));

    await waitFor(() => expect(landingsApi.updateConfig).toHaveBeenCalled());
    const payload = vi.mocked(landingsApi.updateConfig).mock.calls[0][1];
    expect(payload.cta_text_overrides).toEqual({ "2": "Lo quiero ahora" });
  });

  it("saves a background mode for only the selected CTA", async () => {
    const user = userEvent.setup();
    renderEditor();
    await screen.findByText("Banners (2/15)");

    await user.selectOptions(screen.getByLabelText("Fondo CTA #2"), "dark");
    await user.click(screen.getByRole("button", { name: "Guardar configuración" }));

    await waitFor(() => expect(landingsApi.updateConfig).toHaveBeenCalled());
    const payload = vi.mocked(landingsApi.updateConfig).mock.calls[0][1];
    expect(payload.cta_color_modes).toEqual({ "2": "dark" });
  });

  it("removes a CTA background override when changed back to default", async () => {
    const user = userEvent.setup();
    vi.mocked(landingsApi.get).mockResolvedValue({
      ...DETAIL,
      cta_color_modes: { "1": "light" },
    });
    renderEditor();
    await screen.findByText("Banners (2/15)");

    await user.selectOptions(screen.getByLabelText("Fondo CTA #1"), "default");
    await user.click(screen.getByRole("button", { name: "Guardar configuración" }));

    await waitFor(() => expect(landingsApi.updateConfig).toHaveBeenCalled());
    const payload = vi.mocked(landingsApi.updateConfig).mock.calls[0][1];
    expect(payload.cta_color_modes).toEqual({});
  });

  it("preloads existing overrides from the stored landing", async () => {
    vi.mocked(landingsApi.get).mockResolvedValue({
      ...DETAIL,
      cta_text_overrides: { "2": "Lo quiero ahora" },
    });
    renderEditor();
    await screen.findByText("Banners (2/15)");

    expect(screen.getByLabelText("CTA #2")).toHaveValue("Lo quiero ahora");
    expect(screen.getByLabelText("CTA #1")).toHaveValue("");
  });

  it("clearing an override's text removes it from the submitted map", async () => {
    const user = userEvent.setup();
    vi.mocked(landingsApi.get).mockResolvedValue({
      ...DETAIL,
      cta_text_overrides: { "1": "Cómpralo ya", "2": "Lo quiero ahora" },
    });
    renderEditor();
    await screen.findByText("Banners (2/15)");

    await user.clear(screen.getByLabelText("CTA #1"));
    await user.click(screen.getByRole("button", { name: "Guardar configuración" }));

    await waitFor(() => expect(landingsApi.updateConfig).toHaveBeenCalled());
    const payload = vi.mocked(landingsApi.updateConfig).mock.calls[0][1];
    expect(payload.cta_text_overrides).toEqual({ "2": "Lo quiero ahora" });
  });
});
