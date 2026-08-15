/**
 * Tests for the configurable quantity offers and the per-landing accent as the
 * buyer experiences them.
 *
 * The COD form's tiers used to be a hardcoded 1/2/3 list; they are now whatever
 * the merchant configured, priced by the backend. What is worth asserting is the
 * behaviour a merchant can actually change and get wrong:
 *
 * - a blank sub-text renders no second line (the documented way to turn it off);
 * - a discounted tier shows what is owed, with the pre-discount price struck
 *   through, and never the other way round;
 * - the single-unit reference price is shown as a struck-through anchor while
 *   the amount owed stays the real price;
 * - the confirm button always names the selected tier's real total;
 * - the accent reaches the page as CSS custom properties, and a malformed one is
 *   dropped rather than injected.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LandingPage } from "./LandingPage";
import { publicApi } from "../../api";
import type { PublicLanding, PublicLandingOffer } from "../../api";

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

function offer(quantity: number, overrides: Partial<PublicLandingOffer> = {}): PublicLandingOffer {
  const gross = 89900 * quantity;
  return {
    quantity,
    label: quantity === 1 ? "1 unidad" : `${quantity} unidades`,
    sublabel: null,
    discount_percent: 0,
    unit_price: 89900,
    gross,
    total: gross,
    savings: 0,
    compare_at_price: null,
    ...overrides,
  };
}

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
    offers: [offer(1), offer(2), offer(3)],
    ...overrides,
  };
}

async function openForm(landing: PublicLanding) {
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

describe("configurable quantity offers", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders exactly the offers the landing configured", async () => {
    await openForm(makeLanding({ offers: [offer(1), offer(2)] }));

    expect(screen.getByRole("radio", { name: /1 unidad/ })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /2 unidades/ })).toBeInTheDocument();
    // A landing configured for two offers must not show a third.
    expect(screen.queryByRole("radio", { name: /3 unidades/ })).not.toBeInTheDocument();
  });

  it("uses the merchant's own wording for each offer", async () => {
    await openForm(
      makeLanding({
        offers: [
          offer(1, { label: "Solo una" }),
          offer(2, { label: "Llévate dos" }),
          offer(3, { label: "Pack de tres" }),
        ],
      }),
    );

    expect(screen.getByRole("radio", { name: /Solo una/ })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Llévate dos/ })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Pack de tres/ })).toBeInTheDocument();
  });

  it("shows a sub-text when set and no second line when blank", async () => {
    await openForm(
      makeLanding({
        offers: [
          offer(1, { sublabel: null }),
          offer(2, { sublabel: "Ahorra en pedidos grandes" }),
        ],
      }),
    );

    expect(screen.getByText("Ahorra en pedidos grandes")).toBeInTheDocument();
    // The 1-unit tile has no sub-line element at all, rather than an empty one.
    const single = screen.getByRole("radio", { name: /1 unidad/ }).closest("label");
    expect(single?.querySelector(".cod-form__tier-save")).toBeNull();
    const pair = screen.getByRole("radio", { name: /2 unidades/ }).closest("label");
    expect(pair?.querySelector(".cod-form__tier-save")).not.toBeNull();
  });

  it("quotes the discounted total and strikes through the original", async () => {
    await openForm(
      makeLanding({
        offers: [
          offer(1),
          offer(2, {
            discount_percent: 10,
            gross: 179800,
            total: 161820,
            savings: 17980,
          }),
        ],
      }),
    );

    // What is owed, and what it would have been — in that order of prominence.
    expect(screen.getByText("$ 161.820")).toBeInTheDocument();
    const struck = screen.getByText("$ 179.800");
    expect(struck.tagName).toBe("S");
    // The badge states the saving as the percentage the merchant configured.
    expect(screen.getByText("-10%")).toBeInTheDocument();
  });

  it("shows the single-unit reference price as an anchor without charging it", async () => {
    await openForm(
      makeLanding({
        offers: [offer(1, { compare_at_price: 119900 }), offer(2)],
      }),
    );

    const reference = screen.getByText("$ 119.900");
    expect(reference.tagName).toBe("S");
    // The real price is still the one the buyer pays.
    expect(
      screen.getByRole("button", { name: /Confirmar pedido — \$\s?89\.900/ }),
    ).toBeInTheDocument();
  });

  it("names the selected offer's real total on the confirm button", async () => {
    const user = await openForm(
      makeLanding({
        offers: [
          offer(1),
          offer(2, {
            discount_percent: 20,
            gross: 179800,
            total: 143840,
            savings: 35960,
          }),
        ],
      }),
    );

    await user.click(screen.getByRole("radio", { name: /2 unidades/ }));

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /Confirmar pedido — \$\s?143\.840/ }),
      ).toBeInTheDocument(),
    );
  });

  it("falls back to the 1/2/3 tiers when a cached payload has no offers", async () => {
    // Payloads cached before offers existed must still render a usable picker.
    await openForm(makeLanding({ offers: undefined }));

    expect(screen.getByRole("radio", { name: /1 unidad/ })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /3 unidades/ })).toBeInTheDocument();
  });

  it("selects a real offer when the configured list does not start at 1", async () => {
    // Guards the merchant lowering the offer count while a page is open: the
    // form must never sit on a quantity the landing cannot price.
    await openForm(makeLanding({ offers: [offer(2), offer(3)] }));

    expect(screen.getByRole("radio", { name: /2 unidades/ })).toBeChecked();
  });
});

describe("per-landing accent", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("applies the accent palette as CSS custom properties on the page", async () => {
    await openForm(
      makeLanding({
        accent_color: "#2563eb",
        accent_palette: {
          accent: "#2563eb",
          deep: "#2058d3",
          tint: "#f4f5fd",
          ink: "#ffffff",
        },
      }),
    );

    const page = document.querySelector(".lp-page") as HTMLElement;
    expect(page.style.getPropertyValue("--lp-action")).toBe("#2563eb");
    expect(page.style.getPropertyValue("--lp-action-deep")).toBe("#2058d3");
    expect(page.style.getPropertyValue("--lp-action-tint")).toBe("#f4f5fd");
    expect(page.style.getPropertyValue("--lp-action-ink")).toBe("#ffffff");
  });

  it("drops a malformed accent instead of writing it into the style attribute", async () => {
    await openForm(
      makeLanding({
        accent_color: "red; background: url(evil)",
        accent_palette: {
          accent: "javascript:alert(1)",
          deep: "#2058d3",
          tint: "not-a-color",
          ink: "#ffffff",
        },
      }),
    );

    const page = document.querySelector(".lp-page") as HTMLElement;
    // Unset properties fall back to the stylesheet's defaults.
    expect(page.style.getPropertyValue("--lp-action")).toBe("");
    expect(page.style.getPropertyValue("--lp-action-tint")).toBe("");
    // The valid ones still come through.
    expect(page.style.getPropertyValue("--lp-action-deep")).toBe("#2058d3");
  });

  it("leaves the stylesheet defaults in place when no accent is sent", async () => {
    await openForm(makeLanding());

    const page = document.querySelector(".lp-page") as HTMLElement;
    expect(page.style.getPropertyValue("--lp-action")).toBe("");
  });
});

describe("form accent color", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("themes the COD form with its own accent, independent of the CTA's", async () => {
    await openForm(
      makeLanding({
        accent_color: "#2563eb",
        accent_palette: { accent: "#2563eb", deep: "#2058d3", tint: "#f4f5fd", ink: "#ffffff" },
        form_accent_color: "#e11d48",
        form_accent_palette: { accent: "#e11d48", deep: "#b91c3f", tint: "#fdf2f4", ink: "#ffffff" },
      }),
    );

    // The modal (COD form) renders through a portal on document.body, so its
    // style attribute is read directly off the backdrop rather than `.lp-page`.
    const backdrop = document.querySelector(".modal-backdrop") as HTMLElement;
    expect(backdrop.style.getPropertyValue("--lp-form-action")).toBe("#e11d48");
    expect(backdrop.style.getPropertyValue("--lp-form-action-deep")).toBe("#b91c3f");
    // The page's own CTA accent still travels into the modal (it themes the
    // recap/quantity chrome shared with the page) but is distinct from the
    // form accent above.
    expect(backdrop.style.getPropertyValue("--lp-action")).toBe("#2563eb");
  });

  it("falls back to the CTA accent when no form accent was ever set", async () => {
    await openForm(
      makeLanding({
        accent_color: "#2563eb",
        accent_palette: { accent: "#2563eb", deep: "#2058d3", tint: "#f4f5fd", ink: "#ffffff" },
        // Absent form_accent_color/form_accent_palette: payload cached before
        // the feature existed.
      }),
    );

    const backdrop = document.querySelector(".modal-backdrop") as HTMLElement;
    expect(backdrop.style.getPropertyValue("--lp-form-action")).toBe("#2563eb");
  });
});

describe("per-CTA text override", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the override only on the CTA position it targets", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding({
        banners: [
          {
            id: 1,
            alt_text: "Banner 1",
            order_index: 0,
            variants: [{ width: 480, height: 288, format: "webp", url: "https://r2.example/1/480.webp" }],
            top_edge_color: null,
            bottom_edge_color: null,
          },
          {
            id: 2,
            alt_text: "Banner 2",
            order_index: 1,
            variants: [{ width: 480, height: 288, format: "webp", url: "https://r2.example/2/480.webp" }],
            top_edge_color: null,
            bottom_edge_color: null,
          },
        ],
        cta_positions: [1, 2],
        cta_text_overrides: { "2": "Lo quiero ahora" },
      }),
    );
    render(
      <MemoryRouter initialEntries={["/p/set-sartenes"]}>
        <Routes>
          <Route path="/p/:slug" element={<LandingPage />} />
        </Routes>
      </MemoryRouter>,
    );

    const ctas = await screen.findAllByRole("button", { name: /Pedir ahora|Lo quiero ahora/i });
    expect(ctas).toHaveLength(2);
    expect(ctas[0]).toHaveTextContent(/Pedir ahora/);
    expect(ctas[1]).toHaveTextContent("Lo quiero ahora");
  });

  it("falls back to cta_text, then the default label, when a position has no override", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding({
        cta_positions: [1],
        cta_text: "Comprar ya",
        cta_text_overrides: { "2": "Lo quiero ahora" },
      }),
    );
    render(
      <MemoryRouter initialEntries={["/p/set-sartenes"]}>
        <Routes>
          <Route path="/p/:slug" element={<LandingPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("button", { name: "Comprar ya" })).toBeInTheDocument();
  });
});
