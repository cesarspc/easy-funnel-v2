/**
 * Conversion components on the public landing (Requirements 3.27-3.31).
 *
 * The property that matters here is placement: a component with `slot_index: 1`
 * renders between the first and second rendered element, and one with
 * `slot_index: 2` renders between the second and third — whatever those
 * elements happen to be (banner or CTA band).
 */

import { fireEvent, render, screen } from "@testing-library/react";
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
      getLocations: vi.fn().mockResolvedValue({ departments: [] }),
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

  it("renders configured offers, calculated discounts, and an optional landing image", async () => {
    const landing = makeLanding([
      block({
        block_type: "offers_price",
        config: { title: "Escoge tu combo", image_banner_ids: { "2": 1 } },
      }),
    ]);
    landing.offers = [
      {
        quantity: 1,
        label: "Una unidad",
        sublabel: null,
        discount_percent: 0,
        unit_price: 89900,
        gross: 89900,
        total: 89900,
        savings: 0,
        compare_at_price: null,
      },
      {
        quantity: 2,
        label: "Combo x2",
        sublabel: "El más elegido",
        discount_percent: 10,
        unit_price: 89900,
        gross: 179800,
        total: 161820,
        savings: 17980,
        compare_at_price: null,
      },
    ];
    vi.mocked(publicApi.getLanding).mockResolvedValue(landing);
    renderPage();

    await screen.findByText("Escoge tu combo");
    expect(screen.getByText("Una unidad")).toBeInTheDocument();
    expect(screen.getByText("Combo x2")).toBeInTheDocument();
    expect(screen.getByText("-10%")).toBeInTheDocument();
    expect(screen.getByText(/Ahorras/)).toHaveTextContent("17.980");
    expect(screen.getAllByAltText("Banner 1")).toHaveLength(2);
    expect(document.querySelectorAll(".cblock__offer-card")).toHaveLength(2);
  });

  it("renders an inserted CTA, records its click, and opens the shared COD form", async () => {
    const user = userEvent.setup();
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding([
        block({ block_type: "cta", slot_index: 1, config: { text: "Comprar ahora" } }),
      ]),
    );
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Comprar ahora" }));

    expect(publicApi.recordCtaClick).toHaveBeenCalledWith("set-sartenes");
    expect(screen.getByRole("dialog", { name: "Completa tu pedido" })).toBeInTheDocument();
    expect(document.querySelector(".cblock--purchase-cta")).toBeInTheDocument();
  });

  it("buffers only the selected video behind its instant poster and exposes custom playback", async () => {
    const user = userEvent.setup();
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding([
        block({
          block_type: "video_carousel",
          config: { title: "Míralo en acción" },
          videos: [
            {
              id: 10,
              url: "https://r2.example/videos/one/video.mp4",
              poster_url: "https://r2.example/videos/one/poster.webp",
              width: 720,
              height: 1280,
              duration_ms: 10_000,
              caption: "Video uno",
            },
            {
              id: 11,
              url: "https://r2.example/videos/two/video.mp4",
              poster_url: "https://r2.example/videos/two/poster.webp",
              width: 720,
              height: 1280,
              duration_ms: 12_000,
              caption: "Video dos",
            },
          ],
        }),
      ]),
    );
    renderPage();

    await screen.findByRole("button", { name: "Reproducir Video uno" });
    expect(document.querySelector(".cblock__video-poster")).toHaveAttribute(
      "src",
      "https://r2.example/videos/one/poster.webp",
    );
    expect(document.querySelector("video.cblock__video")).toHaveAttribute("preload", "auto");
    expect(document.querySelector("video.cblock__video")).toHaveAttribute(
      "src",
      "https://r2.example/videos/one/video.mp4",
    );
    fireEvent.canPlay(document.querySelector("video.cblock__video") as HTMLVideoElement);
    expect(document.querySelectorAll("video")).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Reproducir Video uno" }));
    expect(play).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: "Cargando Video uno" })).toHaveAttribute(
      "aria-busy",
      "true",
    );
    expect(document.querySelector("video.cblock__video")).not.toHaveAttribute("controls");
    expect(document.querySelector("video.cblock__video")).toHaveAttribute(
      "src",
      "https://r2.example/videos/one/video.mp4",
    );
    fireEvent.playing(document.querySelector("video.cblock__video") as HTMLVideoElement);
    expect(screen.getByRole("button", { name: "Pausar Video uno" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Video siguiente" }));
    expect(document.querySelector(".cblock__video-poster")).toHaveAttribute(
      "src",
      "https://r2.example/videos/two/poster.webp",
    );
    expect(document.querySelectorAll("video")).toHaveLength(1);
    expect(document.querySelector("video.cblock__video")).toHaveAttribute(
      "src",
      "https://r2.example/videos/two/video.mp4",
    );
    expect(screen.getByRole("button", { name: "Reproducir Video dos" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ir al video 2" })).toHaveAttribute(
      "aria-current",
      "true",
    );
    play.mockRestore();
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

  it("inherits the landing dark mode unless a component explicitly overrides it", async () => {
    const landing = makeLanding([
      block({ id: 31, order_index: 0, config: {} }),
      block({ id: 32, order_index: 1, config: { dark_mode: false } }),
    ]);
    landing.blocks_dark_mode = true;
    vi.mocked(publicApi.getLanding).mockResolvedValue(landing);
    renderPage();

    await screen.findByAltText("Banner 1");
    expect(document.querySelectorAll(".cblock-dark-wrap")).toHaveLength(1);
    expect(document.querySelectorAll(".cblock--assurance")).toHaveLength(2);
  });

  it("keeps story labels and icon badges inside the dark-mode scope", async () => {
    const landing = makeLanding([
      block({
        id: 51,
        block_type: "main_problem",
        config: {
          eyebrow: "Si esto te suena familiar",
          title: "Problema principal",
          items: [{ title: "Falta tiempo" }],
        },
      }),
      block({
        id: 52,
        block_type: "solution_presentation",
        config: {
          eyebrow: "La solución",
          title: "Presentamos",
          text: "Un sistema claro",
          items: [{ title: "Sistema de ventas" }],
        },
      }),
      block({
        id: 53,
        block_type: "audience",
        config: {
          title: "Para quién es",
          positive_title: "ES PARA TI",
          positive_items: ["Quieres avanzar"],
          negative_title: "NO ES PARA TI",
          negative_items: ["No quieres actuar"],
        },
      }),
      block({
        id: 54,
        block_type: "guarantee",
        config: {
          eyebrow: "Compra protegida",
          title: "Garantía",
          text: "Compra sin riesgo",
          days: 7,
          benefits: [{ title: "Riesgo cero" }],
        },
      }),
    ]);
    landing.blocks_dark_mode = true;
    vi.mocked(publicApi.getLanding).mockResolvedValue(landing);
    renderPage();

    await screen.findByText("Problema principal");
    expect(document.querySelectorAll(".cblock-dark-wrap .cblock__story-eyebrow")).toHaveLength(3);
    expect(document.querySelectorAll(".cblock-dark-wrap .cblock__story-icon")).toHaveLength(2);
    expect(
      document.querySelector(".cblock-dark-wrap .cblock__audience-card--yes header > span"),
    ).not.toBeNull();
  });

  it("uses the landing block accent until the component supplies its own override", async () => {
    const landing = makeLanding([
      block({
        block_type: "benefits",
        config: { items: ["Acento general", "Segundo beneficio"] },
      }),
      block({
        id: 42,
        block_type: "benefits",
        slot_index: 2,
        config: { items: ["Acento propio", "Otro beneficio"] },
        accent_palette: {
          accent: "#dc2626",
          deep: "#991b1b",
          tint: "#fee2e2",
          ink: "#ffffff",
        },
      }),
    ]);
    landing.blocks_accent_palette = {
      accent: "#7c3aed",
      deep: "#5b21b6",
      tint: "#ede9fe",
      ink: "#ffffff",
    };
    vi.mocked(publicApi.getLanding).mockResolvedValue(landing);
    renderPage();

    const inherited = (await screen.findByText("Acento general")).closest(".cblock");
    const overridden = screen.getByText("Acento propio").closest(".cblock");
    expect(inherited).toHaveStyle({ "--lp-form-action": "#7c3aed" });
    expect(overridden).toHaveStyle({ "--lp-form-action": "#dc2626" });
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
    expect(screen.queryByText(/Ahorras/)).not.toBeInTheDocument();
  });

  it("rebuilds the legacy price block exactly from three consecutive modular components", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding([
        block({
          id: 1,
          block_type: "offer_price",
          slot_index: 1,
          config: { compare_at_price: 129900, note: "Escoge más unidades" },
        }),
        block({
          id: 2,
          block_type: "price_summary",
          slot_index: 2,
          order_index: 0,
          config: { compare_at_price: 129900 },
        }),
        block({ id: 3, block_type: "store_trust", slot_index: 2, order_index: 1 }),
        block({
          id: 4,
          block_type: "purchase_benefits",
          slot_index: 2,
          order_index: 2,
          config: { note: "Escoge más unidades" },
        }),
      ]),
    );
    renderPage();

    await screen.findByAltText("Banner 1");
    const legacy = document.querySelector(".cblock--price");
    const price = document.querySelector(".cblock--price-price");
    const trust = document.querySelector(".cblock--price-trust");
    const benefits = document.querySelector(".cblock--price-benefits");
    expect(legacy).not.toBeNull();
    expect(price).toHaveClass("cblock--price-joined-after");
    expect(trust).toHaveClass("cblock--price-joined-before", "cblock--price-joined-after");
    expect(benefits).toHaveClass("cblock--price-joined-before");
    expect(price?.querySelector(".cblock__price-card")?.innerHTML).toBe(
      legacy?.querySelector(".cblock__price-card")?.innerHTML,
    );
    expect(trust?.querySelector(".cblock__trust-badge")?.innerHTML).toBe(
      legacy?.querySelector(".cblock__trust-badge")?.innerHTML,
    );
    expect(benefits?.querySelector(".cblock__price-info")?.innerHTML).toBe(
      legacy?.querySelector(".cblock__price-info")?.innerHTML,
    );
  });

  it("renders the standard spacer as an empty standalone component", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding([block({ block_type: "spacer", slot_index: 1 })]),
    );
    renderPage();

    await screen.findByAltText("Banner 1");
    const spacer = document.querySelector(".cblock--spacer");
    expect(spacer).toBeInTheDocument();
    expect(spacer).toBeEmptyDOMElement();
    expect(spacer).toHaveAttribute("aria-hidden", "true");
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

  it("renders reviews with an accessible rating label", async () => {
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

  it("renders the complete mobile-first story sequence and rich guarantee", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding([
        block({
          id: 21,
          block_type: "main_problem",
          slot_index: 1,
          config: {
            title: "La razón principal",
            highlight: "todavía no lo logras",
            items: [{ title: "Te falta tiempo", text: "El día no alcanza." }],
          },
        }),
        block({
          id: 22,
          block_type: "solution_presentation",
          slot_index: 2,
          config: {
            bridge_text: "Esta solución fue creada para ti",
            title: "Presentamos el método",
            text: "Un sistema simple.",
            items: [{ title: "Primer pilar", text: "Todo lo esencial." }],
            final_title: "Un solo sistema",
            final_highlight: "Resultados reales",
          },
        }),
        block({
          id: 23,
          block_type: "how_it_works",
          slot_index: 3,
          config: {
            title: "Cómo funciona",
            steps: [{ kicker: "Día 1", title: "Empieza aquí", text: "Primer paso." }],
          },
        }),
        block({
          id: 24,
          block_type: "audience",
          slot_index: 4,
          config: {
            title: "Para quién es",
            positive_title: "ES PARA TI",
            positive_items: ["Quieres una solución clara"],
            negative_title: "NO ES PARA TI",
            negative_items: ["Buscas resultados sin esfuerzo"],
          },
        }),
        block({
          id: 25,
          block_type: "moment",
          slot_index: 5,
          config: {
            title: "Sigues esperando el",
            highlight: "momento perfecto",
            text: "El momento perfecto no existe.",
          },
        }),
        block({
          id: 26,
          block_type: "guarantee",
          slot_index: 6,
          config: {
            title: "Garantía",
            text: "Tu compra está protegida.",
            days: 7,
            benefits: [{ title: "Riesgo cero", text: "Sin preguntas." }],
          },
        }),
      ]),
    );
    renderPage();

    await screen.findByAltText("Banner 1");
    expect(screen.getByText("La razón principal")).toBeInTheDocument();
    expect(screen.getByText("Esta solución fue creada para ti")).toBeInTheDocument();
    expect(screen.getByText("Empieza aquí")).toBeInTheDocument();
    expect(screen.getByText("Quieres una solución clara")).toBeInTheDocument();
    expect(screen.getByText("momento perfecto")).toBeInTheDocument();
    expect(screen.getByText("Total de 7 días")).toBeInTheDocument();
    expect(document.querySelectorAll(".cblock--story")).toHaveLength(6);
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
    expect(screen.getByLabelText("Nombre")).toBeInTheDocument();
    expect(screen.getByLabelText("Apellido")).toBeInTheDocument();
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
