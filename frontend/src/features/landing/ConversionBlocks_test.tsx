/**
 * Conversion components on the public landing (Requirements 3.27-3.31).
 *
 * The property that matters here is placement: a component with `slot_index: 1`
 * renders between the first and second rendered element, and one with
 * `slot_index: 2` renders between the second and third — whatever those
 * elements happen to be (banner or CTA band).
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LandingPage } from "./LandingPage";
import { publicApi } from "../../api";
import type { ConversionBlock, PublicLanding } from "../../api";

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

/** Three banners with a CTA after each: six rendered elements, seven slots. */
function makeLanding(blocks: ConversionBlock[]): PublicLanding {
  return {
    landing_id: 1,
    product_id: 1,
    product_name: "Set de sartenes",
    product_sku: "SKU-1",
    product_price: 89900,
    slug: "set-sartenes",
    banners: [1, 2, 3].map((id) => ({
      id,
      alt_text: `Banner ${id}`,
      order_index: id - 1,
      variants: [{ width: 480, height: 288, format: "webp" as const, url: `https://r2.example/${id}.webp` }],
      top_edge_color: null,
      bottom_edge_color: null,
    })),
    cta_positions: [1, 2, 3],
    cta_backgrounds: [],
    form_presentation: "modal",
    cta_band_style: "gradient",
    blocks,
  };
}

function block(overrides: Partial<ConversionBlock>): ConversionBlock {
  return {
    id: 1,
    block_type: "cod_assurance",
    slot_index: 1,
    order_index: 0,
    config: {},
    accent_palette: null,
    ...overrides,
  };
}

/** Class names of the page sequence, in DOM order. */
function sequenceClasses(): string[] {
  const container = document.querySelector(".lp-page__banners");
  return Array.from(container?.children ?? []).map((child) => child.className);
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/p/set-sartenes"]}>
      <Routes>
        <Route path="/p/:slug" element={<LandingPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("conversion components on the landing", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders nothing extra when no component is placed", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(makeLanding([]));
    renderPage();

    await screen.findByAltText("Banner 1");
    expect(document.querySelectorAll(".cblock")).toHaveLength(0);
  });

  it("places a component in slot 1, between the first banner and the first CTA", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding([block({ slot_index: 1, config: { note: "Cobertura nacional" } })]),
    );
    renderPage();

    await screen.findByAltText("Banner 1");

    const classes = sequenceClasses();
    // banner 1, component, CTA band 1, banner 2, ...
    expect(classes[0]).toContain("banner");
    expect(classes[1]).toContain("cblock--assurance");
    expect(classes[2]).toContain("lp-page__cta-band");
    expect(screen.getByText("Cobertura nacional")).toBeInTheDocument();
    expect(screen.getByText("Pagas al recibir")).toBeInTheDocument();
  });

  it("places a component in slot 2, between the first CTA and the second banner", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding([
        block({ block_type: "benefits", slot_index: 2, config: { items: ["Antiadherente", "Apta para gas"] } }),
      ]),
    );
    renderPage();

    await screen.findByAltText("Banner 1");

    const classes = sequenceClasses();
    expect(classes[1]).toContain("lp-page__cta-band");
    expect(classes[2]).toContain("cblock--benefits");
    expect(classes[3]).toContain("banner");
    expect(screen.getByText("Antiadherente")).toBeInTheDocument();
  });

  it("places a component above everything with slot 0", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding([block({ slot_index: 0 })]),
    );
    renderPage();

    await screen.findByAltText("Banner 1");
    expect(sequenceClasses()[0]).toContain("cblock--assurance");
  });

  it("renders several components in one slot in their stored order", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding([
        block({ id: 2, block_type: "guarantee", slot_index: 1, order_index: 1, config: { title: "Garantía", text: "30 días" } }),
        block({ id: 1, block_type: "cod_assurance", slot_index: 1, order_index: 0 }),
      ]),
    );
    renderPage();

    await screen.findByAltText("Banner 1");

    const classes = sequenceClasses();
    expect(classes[1]).toContain("cblock--assurance");
    expect(classes[2]).toContain("cblock--guarantee");
  });

  it("renders a component placed past the sequence at the end instead of dropping it", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding([block({ slot_index: 25 })]),
    );
    renderPage();

    await screen.findByAltText("Banner 1");

    const classes = sequenceClasses();
    expect(classes[classes.length - 1]).toContain("cblock--assurance");
  });

  it("computes the saving from the product price, never from the block", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding([
        block({ block_type: "offer_price", slot_index: 1, config: { compare_at_price: 129900 } }),
      ]),
    );
    renderPage();

    await screen.findByAltText("Banner 1");

    // 89900 of 129900 -> saves 40000, 31%.
    expect(screen.getByLabelText("31% de descuento")).toBeInTheDocument();
    expect(screen.getByText(/de descuento/)).toHaveTextContent("40.000");
  });

  it("ignores a reference price below the selling price rather than showing a negative saving", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding([
        block({ block_type: "offer_price", slot_index: 1, config: { compare_at_price: 1000 } }),
      ]),
    );
    renderPage();

    await screen.findByAltText("Banner 1");
    expect(screen.queryByText(/de descuento/)).not.toBeInTheDocument();
    expect(screen.queryByText(/^DE /)).not.toBeInTheDocument();
  });

  it("renders a comparison table when the block stores rows, instead of the plain checklist", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding([
        block({
          block_type: "benefits",
          slot_index: 1,
          config: {
            ours_label: "Este de 2L",
            rows: [
              { label: "Capacidad", common: "Muy pequeña", ours: "2 litros" },
              { label: "Material", common: "Plástico", ours: "Acero inoxidable" },
            ],
          },
        }),
      ]),
    );
    renderPage();

    await screen.findByAltText("Banner 1");

    expect(document.querySelector(".cblock__compare")).toBeInTheDocument();
    expect(screen.getByText("Común")).toBeInTheDocument();
    expect(screen.getByText("Este de 2L")).toBeInTheDocument();
    expect(screen.getByText("2 litros")).toBeInTheDocument();
  });

  it("falls back to the plain checklist for a legacy items-only benefits config", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding([
        block({ block_type: "benefits", slot_index: 1, config: { items: ["Antiadherente", "Apta para gas"] } }),
      ]),
    );
    renderPage();

    await screen.findByAltText("Banner 1");
    expect(document.querySelector(".cblock__compare")).not.toBeInTheDocument();
    expect(screen.getByText("Antiadherente")).toBeInTheDocument();
  });

  it("renders the urgency card for an announcement_bar with items", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding([
        block({
          block_type: "announcement_bar",
          slot_index: 0,
          config: {
            title: "Aprovecha hoy",
            items: [
              { lead: "Pedidos antes de las 2:00 p.m.", text: "salen el mismo día" },
              { lead: "Envío GRATIS", text: "a todo Colombia esta semana" },
            ],
            stock_label: "Stock disponible — quedan pocas unidades",
            stock_percent: 70,
          },
        }),
      ]),
    );
    renderPage();

    await screen.findByAltText("Banner 1");
    expect(document.querySelector(".cblock--urgency")).toBeInTheDocument();
    expect(screen.getByText("Pedidos antes de las 2:00 p.m.")).toBeInTheDocument();
    expect(screen.getByText("Stock disponible — quedan pocas unidades")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "70");
  });

  it("renders the legacy single-line strip for an announcement_bar with only text", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding([
        block({ block_type: "announcement_bar", slot_index: 0, config: { text: "Envío gratis hoy" } }),
      ]),
    );
    renderPage();

    await screen.findByAltText("Banner 1");
    expect(document.querySelector(".cblock--announcement")).toBeInTheDocument();
    expect(document.querySelector(".cblock--urgency")).not.toBeInTheDocument();
    expect(screen.getByText("Envío gratis hoy")).toBeInTheDocument();
  });

  it("renders FAQ answers in collapsed native disclosures", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding([
        block({
          block_type: "faq",
          slot_index: 3,
          config: {
            items: [{ question: "¿Cuándo llega?", answer: "Entre 1 y 3 días hábiles." }],
          },
        }),
      ]),
    );
    const user = userEvent.setup();
    renderPage();

    await screen.findByAltText("Banner 1");

    const details = document.querySelector("details");
    expect(details).not.toBeNull();
    expect(details).not.toHaveAttribute("open");

    await user.click(screen.getByText("¿Cuándo llega?"));
    expect(details).toHaveAttribute("open");
  });

  it("renders reviews with an accessible rating label (detailed variant, default)", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding([
        block({
          block_type: "reviews",
          slot_index: 4,
          config: {
            items: [
              { name: "Cliente de ejemplo", city: "Cali", text: "Llegó en dos días.", rating: 5 },
            ],
          },
        }),
      ]),
    );
    renderPage();

    await screen.findByAltText("Banner 1");
    expect(screen.getByLabelText("5 de 5 estrellas")).toBeInTheDocument();
    expect(screen.getByText("Cliente de ejemplo · Cali")).toBeInTheDocument();
  });

  it("renders the verified variant with order, phone, and date proof", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding([
        block({
          block_type: "reviews",
          slot_index: 4,
          config: {
            variant: "verified",
            rating: 4.9,
            rating_count: 5,
            items: [
              {
                name: "Brayan S.",
                city: "Pereira, Risaralda",
                text: "Muele carne y verdura en segundos.",
                rating: 5,
                channel: "Instagram",
                order_id: "MO-11170",
                phone: "+57 313 141 51**",
                date: "2026-06-08",
              },
            ],
          },
        }),
      ]),
    );
    renderPage();

    await screen.findByAltText("Banner 1");
    expect(document.querySelector(".cblock--reviews-verified")).toBeInTheDocument();
    expect(screen.getByText("Compra verificada · Instagram")).toBeInTheDocument();
    expect(screen.getByText("Pedido #MO-11170 · +57 313 141 51** · 2026-06-08")).toBeInTheDocument();
  });

  it("skips a component whose content is unusable instead of failing the page", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding([block({ block_type: "benefits", slot_index: 1, config: {} })]),
    );
    renderPage();

    await screen.findByAltText("Banner 1");
    expect(document.querySelectorAll(".cblock")).toHaveLength(0);
    expect(screen.getAllByRole("button", { name: /Pedir ahora/i }).length).toBeGreaterThan(0);
  });

  it("keeps the CTA pop-up working with components on the page", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding([block({ slot_index: 1 })]),
    );
    const user = userEvent.setup();
    renderPage();

    await user.click((await screen.findAllByRole("button", { name: /Pedir ahora/i }))[0]);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByLabelText("Nombre completo")).toBeInTheDocument();
  });
});

describe("payloads without the feature", () => {
  beforeEach(() => {
    const landing = makeLanding([]);
    delete landing.blocks;
    vi.mocked(publicApi.getLanding).mockResolvedValue(landing);
  });

  it("renders the page when the payload predates conversion components", async () => {
    renderPage();

    await screen.findByAltText("Banner 1");
    expect(document.querySelectorAll(".cblock")).toHaveLength(0);
    expect(screen.getAllByRole("button", { name: /Pedir ahora/i })).toHaveLength(3);
  });
});
