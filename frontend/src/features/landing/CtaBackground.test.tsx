/**
 * CTA band background behavior (see docs/backend.md, Requirements 3.9-3.15).
 *
 * `cta_positions` and `CtaBackground.position` are both **1-based** banner
 * positions — the value returned by the backend's `compute_cta_positions`.
 * The fixtures below mirror that contract exactly; treating those values as
 * array indices is the regression these tests exist to catch.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LandingPage } from "./LandingPage";
import { publicApi } from "../../api";
import type { Banner, PublicLanding } from "../../api";
import { safeColor } from "../../utils";

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

function makeBanner(
  id: number,
  orderIndex: number,
  edges: { top?: string | null; bottom?: string | null } = {},
): Banner {
  return {
    id,
    alt_text: `Banner ${id}`,
    order_index: orderIndex,
    variants: [
      { width: 480, format: "webp", url: `https://r2.example/${id}/480.webp` },
      { width: 480, format: "jpeg", url: `https://r2.example/${id}/480.jpg` },
    ],
    top_edge_color: edges.top ?? null,
    bottom_edge_color: edges.bottom ?? null,
  };
}

/** A blend band, as the backend emits it between two banners with flat edges. */
function blendBand(position: number, top: string, bottom: string, foreground: "light" | "dark") {
  return { position, top_color: top, bottom_color: bottom, blend_color: top, foreground, source: "blend" as const };
}

function makeLanding(overrides: Partial<PublicLanding> = {}): PublicLanding {
  return {
    landing_id: 1,
    product_id: 1,
    product_name: "Test Product",
    product_sku: "TST-001",
    product_price: 50000,
    slug: "test-product",
    banners: [
      makeBanner(1, 0, { bottom: "#112233" }),
      makeBanner(2, 1, { top: "#334455", bottom: "#556677" }),
      makeBanner(3, 2, { top: "#778899" }),
    ],
    cta_positions: [1, 2],
    cta_backgrounds: [
      blendBand(1, "#112233", "#334455", "light"),
      blendBand(2, "#556677", "#778899", "dark"),
    ],
    form_presentation: "inline",
    cta_band_style: "gradient",
    ...overrides,
  };
}

function renderAtSlug(slug = "test-product") {
  return render(
    <MemoryRouter initialEntries={[`/p/${slug}`]}>
      <Routes>
        <Route path="/p/:slug" element={<LandingPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function bands(): HTMLElement[] {
  return Array.from(document.querySelectorAll<HTMLElement>(".lp-page__cta-band"));
}

function bandColors(band: HTMLElement) {
  return {
    top: band.style.getPropertyValue("--cta-band-top"),
    bottom: band.style.getPropertyValue("--cta-band-bottom"),
    blend: band.style.getPropertyValue("--cta-band-blend"),
    foreground: band.dataset.ctaForeground,
    source: band.dataset.ctaSource,
  };
}

/** Kept out of `bandColors` so its exhaustive `toEqual` assertions still read. */
function bandStyleOf(band: HTMLElement) {
  return band.dataset.ctaBandStyle;
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("CTA band: gradient between two banners", () => {
  beforeEach(() => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(makeLanding());
  });

  it("paints the gradient from the bottom edge above to the top edge below", async () => {
    renderAtSlug();
    await screen.findByAltText("Banner 1");

    // Position 1 sits between banner 1 (bottom #112233) and banner 2 (top #334455).
    expect(bandColors(bands()[0])).toMatchObject({
      top: "#112233",
      bottom: "#334455",
      source: "blend",
    });

    // Position 2 sits between banner 2 (bottom #556677) and banner 3 (top #778899).
    expect(bandColors(bands()[1])).toMatchObject({
      top: "#556677",
      bottom: "#778899",
      source: "blend",
    });
  });

  it("carries the backend's foreground mode onto each band", async () => {
    renderAtSlug();
    await screen.findByAltText("Banner 1");

    expect(bands()[0].dataset.ctaForeground).toBe("light");
    expect(bands()[1].dataset.ctaForeground).toBe("dark");
  });

  it("places each band immediately after its 1-based banner", async () => {
    renderAtSlug();
    await screen.findByAltText("Banner 1");

    // The band for position 1 must be the sibling that follows banner 1.
    const firstBanner = document.querySelector('[data-banner-id="1"]');
    expect(firstBanner?.nextElementSibling).toHaveClass("lp-page__cta-band");
    expect(firstBanner?.nextElementSibling).toHaveAttribute("data-cta-source", "blend");
  });
});

describe("CTA band: solid and fallback treatments", () => {
  it("renders a solid band when only the banner above has a usable edge", async () => {
    // `source: above` arrives with both endpoints already equal.
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding({
        banners: [makeBanner(1, 0, { bottom: "#aabbcc" })],
        cta_positions: [1],
        cta_backgrounds: [
          {
            position: 1,
            top_color: "#aabbcc",
            bottom_color: "#aabbcc",
            blend_color: "#aabbcc",
            foreground: "dark",
            source: "above",
          },
        ],
      }),
    );

    renderAtSlug();
    await screen.findByAltText("Banner 1");

    const colors = bandColors(bands()[0]);
    expect(colors.source).toBe("above");
    expect(colors.top).toBe("#aabbcc");
    // Equal endpoints are what make the gradient render as a flat fill.
    expect(colors.bottom).toBe(colors.top);
  });

  it("renders a solid band when only the banner below has a usable edge", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding({
        cta_positions: [1],
        cta_backgrounds: [
          {
            position: 1,
            top_color: "#ddeeff",
            bottom_color: "#ddeeff",
            blend_color: "#ddeeff",
            foreground: "dark",
            source: "below",
          },
        ],
      }),
    );

    renderAtSlug();
    await screen.findByAltText("Banner 1");

    const colors = bandColors(bands()[0]);
    expect(colors.source).toBe("below");
    expect(colors.top).toBe("#ddeeff");
    expect(colors.bottom).toBe("#ddeeff");
  });

  it("sets no color properties for source 'fallback', leaving the neutral token", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding({
        banners: [makeBanner(1, 0)],
        cta_positions: [1],
        cta_backgrounds: [
          {
            position: 1,
            top_color: null,
            bottom_color: null,
            blend_color: null,
            foreground: null,
            source: "fallback",
          },
        ],
      }),
    );

    renderAtSlug();
    await screen.findByAltText("Banner 1");

    expect(bandColors(bands()[0])).toEqual({
      top: "",
      bottom: "",
      blend: "",
      foreground: "fallback",
      source: "fallback",
    });
  });

  it("renders a CTA after the final banner as a solid band", async () => {
    // 2 banners, CTA after both: position 2 has only the banner above.
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding({
        banners: [
          makeBanner(1, 0, { bottom: "#111111" }),
          makeBanner(2, 1, { top: "#222222", bottom: "#333333" }),
        ],
        cta_positions: [1, 2],
        cta_backgrounds: [
          blendBand(1, "#111111", "#222222", "light"),
          {
            position: 2,
            top_color: "#333333",
            bottom_color: "#333333",
            blend_color: "#333333",
            foreground: "light",
            source: "above",
          },
        ],
      }),
    );

    renderAtSlug();
    await screen.findByAltText("Banner 1");

    expect(bands()).toHaveLength(2);
    const last = bandColors(bands()[1]);
    expect(last.source).toBe("above");
    expect(last.top).toBe("#333333");
    expect(last.bottom).toBe("#333333");
  });
});

describe("CTA band: position alignment", () => {
  it("matches 1-based positions even when cta_backgrounds is unordered", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding({
        cta_positions: [1, 2],
        cta_backgrounds: [
          blendBand(2, "#aaaaaa", "#bbbbbb", "dark"),
          blendBand(1, "#cccccc", "#dddddd", "light"),
        ],
      }),
    );

    renderAtSlug();
    await screen.findByAltText("Banner 1");

    expect(bandColors(bands()[0])).toMatchObject({ top: "#cccccc", foreground: "light" });
    expect(bandColors(bands()[1])).toMatchObject({ top: "#aaaaaa", foreground: "dark" });
  });

  it("ignores a duplicate position, keeping the first descriptor", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding({
        cta_positions: [1],
        cta_backgrounds: [
          blendBand(1, "#111111", "#222222", "light"),
          blendBand(1, "#999999", "#888888", "dark"),
        ],
      }),
    );

    renderAtSlug();
    await screen.findByAltText("Banner 1");

    expect(bandColors(bands()[0])).toMatchObject({ top: "#111111", foreground: "light" });
  });

  it("ignores a background for a position that has no CTA", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding({
        cta_positions: [1],
        cta_backgrounds: [
          blendBand(1, "#111111", "#222222", "light"),
          blendBand(7, "#ff0000", "#00ff00", "dark"), // out of range
        ],
      }),
    );

    renderAtSlug();
    await screen.findByAltText("Banner 1");

    const painted = bands().map((band) => bandColors(band).top);
    expect(painted).not.toContain("#ff0000");
  });
});

describe("CTA band: CTA placement modes", () => {
  it("after_every: one CTA per banner and no duplicate trailing CTA", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding({
        cta_positions: [1, 2, 3],
        cta_backgrounds: [
          blendBand(1, "#111111", "#222222", "light"),
          blendBand(2, "#333333", "#444444", "dark"),
          blendBand(3, "#555555", "#555555", "light"),
        ],
      }),
    );

    renderAtSlug();
    await screen.findByAltText("Banner 1");

    expect(screen.getAllByRole("button", { name: /Pedir ahora/i })).toHaveLength(3);
    expect(bands()).toHaveLength(3);
  });

  it("every_n: a CTA only at each completed interval, plus a trailing CTA", async () => {
    // interval 2 over 3 banners -> position 2 only.
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding({
        cta_positions: [2],
        cta_backgrounds: [blendBand(2, "#556677", "#778899", "dark")],
      }),
    );

    renderAtSlug();
    await screen.findByAltText("Banner 1");

    // The band for position 2 follows banner 2, never banner 1. The sequence is
    // one flat column (banners, CTA bands, and conversion components are
    // siblings), so "no band here" is asserted on the element that follows.
    expect(document.querySelector('[data-banner-id="1"]')?.nextElementSibling).not.toHaveClass(
      "lp-page__cta-band",
    );
    expect(document.querySelector('[data-banner-id="2"]')?.nextElementSibling).toHaveClass(
      "lp-page__cta-band",
    );

    // Position 3 is uncovered, so a trailing CTA closes the page.
    expect(screen.getAllByRole("button", { name: /Pedir ahora/i })).toHaveLength(2);
    expect(bandColors(bands()[1]).source).toBe("fallback");
  });

  it("fixed_positions: CTAs only at the configured positions", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding({
        cta_positions: [3],
        cta_backgrounds: [
          {
            position: 3,
            top_color: "#778899",
            bottom_color: "#778899",
            blend_color: "#778899",
            foreground: "dark",
            source: "above",
          },
        ],
      }),
    );

    renderAtSlug();
    await screen.findByAltText("Banner 1");

    expect(screen.getAllByRole("button", { name: /Pedir ahora/i })).toHaveLength(1);
    expect(document.querySelector('[data-banner-id="3"]')?.nextElementSibling).toHaveClass(
      "lp-page__cta-band",
    );
    expect(bandColors(bands()[0]).top).toBe("#778899");
  });

  it("renders one CTA for a single-banner landing", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding({
        banners: [makeBanner(1, 0, { bottom: "#aabbcc" })],
        cta_positions: [1],
        cta_backgrounds: [
          {
            position: 1,
            top_color: "#aabbcc",
            bottom_color: "#aabbcc",
            blend_color: "#aabbcc",
            foreground: "dark",
            source: "above",
          },
        ],
      }),
    );

    renderAtSlug();
    await screen.findByAltText("Banner 1");

    expect(screen.getAllByRole("button", { name: /Pedir ahora/i })).toHaveLength(1);
    expect(bands()).toHaveLength(1);
  });

  it("handles the 15-banner maximum with a CTA after every banner", async () => {
    const banners = Array.from({ length: 15 }, (_, index) =>
      makeBanner(index + 1, index, { top: "#fe0002", bottom: "#fe0002" }),
    );
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding({
        banners,
        cta_positions: Array.from({ length: 15 }, (_, index) => index + 1),
        cta_backgrounds: Array.from({ length: 15 }, (_, index) =>
          blendBand(index + 1, "#fe0002", "#fe0002", "light"),
        ),
      }),
    );

    renderAtSlug();
    await screen.findByAltText("Banner 1");

    expect(bands()).toHaveLength(15);
    expect(screen.getAllByRole("button", { name: /Pedir ahora/i })).toHaveLength(15);
    // Every band is painted; none silently fell back.
    expect(bands().every((band) => bandColors(band).source === "blend")).toBe(true);
  });
});

describe("CTA band: degraded payloads", () => {
  it("does not crash when cta_backgrounds is absent (older or cached response)", async () => {
    const legacy: Omit<PublicLanding, "cta_backgrounds"> = {
      landing_id: 1,
      product_id: 1,
      product_name: "Test Product",
      product_sku: "TST-001",
      product_price: 50000,
      slug: "test-product",
      banners: [makeBanner(1, 0)],
      cta_positions: [1],
      form_presentation: "inline",
    };
    vi.mocked(publicApi.getLanding).mockResolvedValue(legacy as PublicLanding);

    renderAtSlug();

    expect(await screen.findByAltText("Banner 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Pedir ahora/i })).toBeInTheDocument();
    expect(bandColors(bands()[0])).toMatchObject({ foreground: "fallback", source: "fallback" });
  });

  it("drops invalid color strings instead of emitting them as CSS", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding({
        banners: [makeBanner(1, 0)],
        cta_positions: [1],
        cta_backgrounds: [
          {
            position: 1,
            top_color: "red; background: url(https://evil.example/x)",
            bottom_color: "rgb(255,0,0)",
            blend_color: "javascript:alert(1)",
            foreground: "light",
            source: "blend",
          },
        ],
      }),
    );

    renderAtSlug();
    await screen.findByAltText("Banner 1");

    const band = bands()[0];
    expect(bandColors(band)).toMatchObject({ top: "", bottom: "", blend: "" });
    // With nothing paintable, the neutral treatment wins over the claimed mode.
    expect(band.dataset.ctaForeground).toBe("fallback");
    expect(band.getAttribute("style") ?? "").not.toContain("evil.example");
  });

  it("never paints half a gradient when only one endpoint is usable", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding({
        banners: [makeBanner(1, 0)],
        cta_positions: [1],
        cta_backgrounds: [
          {
            position: 1,
            top_color: "#123456",
            bottom_color: "not-a-color",
            blend_color: null,
            foreground: "light",
            source: "blend",
          },
        ],
      }),
    );

    renderAtSlug();
    await screen.findByAltText("Banner 1");

    const colors = bandColors(bands()[0]);
    // Both endpoints resolve, or neither does.
    expect(colors.top).toBe("#123456");
    expect(colors.bottom).toBe("#123456");
  });

  it("falls back to blend_color when the endpoints are unusable", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      makeLanding({
        banners: [makeBanner(1, 0)],
        cta_positions: [1],
        cta_backgrounds: [
          {
            position: 1,
            top_color: null,
            bottom_color: null,
            blend_color: "#2b2b2b",
            foreground: "light",
            source: "blend",
          },
        ],
      }),
    );

    renderAtSlug();
    await screen.findByAltText("Banner 1");

    expect(bandColors(bands()[0])).toMatchObject({
      top: "#2b2b2b",
      bottom: "#2b2b2b",
      foreground: "light",
    });
  });
});

describe("CTA band: landing-level paint style", () => {
  /** A band whose three colors are all distinct, so the choice is observable. */
  const DISTINCT = {
    position: 1,
    top_color: "#102030",
    bottom_color: "#f0e0d0",
    blend_color: "#8a8078",
    foreground: "dark" as const,
    source: "blend" as const,
  };

  function landingWithStyle(overrides: Partial<PublicLanding> = {}): PublicLanding {
    return makeLanding({
      banners: [makeBanner(1, 0, { bottom: "#102030" }), makeBanner(2, 1, { top: "#f0e0d0" })],
      cta_positions: [1],
      cta_backgrounds: [DISTINCT],
      ...overrides,
    });
  }

  it("keeps the two endpoints distinct for 'gradient'", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(landingWithStyle());
    renderAtSlug();
    await screen.findByAltText("Banner 1");

    expect(bandColors(bands()[0])).toMatchObject({ top: "#102030", bottom: "#f0e0d0" });
    expect(bandStyleOf(bands()[0])).toBe("gradient");
  });

  it("fills both endpoints with the blend color for 'solid'", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      landingWithStyle({ cta_band_style: "solid" }),
    );
    renderAtSlug();
    await screen.findByAltText("Banner 1");

    // Equal endpoints are what make the one gradient rule render a flat fill,
    // so 'solid' needs no CSS of its own.
    expect(bandColors(bands()[0])).toMatchObject({ top: "#8a8078", bottom: "#8a8078" });
    expect(bandStyleOf(bands()[0])).toBe("solid");
  });

  it("treats a payload with no style at all as 'gradient'", async () => {
    const legacy = landingWithStyle();
    delete legacy.cta_band_style;
    vi.mocked(publicApi.getLanding).mockResolvedValue(legacy);
    renderAtSlug();
    await screen.findByAltText("Banner 1");

    expect(bandColors(bands()[0])).toMatchObject({ top: "#102030", bottom: "#f0e0d0" });
    expect(bandStyleOf(bands()[0])).toBe("gradient");
  });

  it("treats an unrecognized style as 'gradient'", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue({
      ...landingWithStyle(),
      cta_band_style: "fade" as never,
    });
    renderAtSlug();
    await screen.findByAltText("Banner 1");

    expect(bandColors(bands()[0])).toMatchObject({ top: "#102030", bottom: "#f0e0d0" });
    expect(bandStyleOf(bands()[0])).toBe("gradient");
  });

  it("falls back to the one usable endpoint when 'solid' has no blend color", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      landingWithStyle({
        cta_band_style: "solid",
        cta_backgrounds: [{ ...DISTINCT, blend_color: null, bottom_color: null }],
      }),
    );
    renderAtSlug();
    await screen.findByAltText("Banner 1");

    expect(bandColors(bands()[0])).toMatchObject({ top: "#102030", bottom: "#102030" });
  });

  it("still shows the neutral token for an unpainted band under 'solid'", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(
      landingWithStyle({
        cta_band_style: "solid",
        cta_backgrounds: [
          {
            position: 1,
            top_color: null,
            bottom_color: null,
            blend_color: null,
            foreground: null,
            source: "fallback",
          },
        ],
      }),
    );
    renderAtSlug();
    await screen.findByAltText("Banner 1");

    expect(bandColors(bands()[0])).toEqual({
      top: "",
      bottom: "",
      blend: "",
      foreground: "fallback",
      source: "fallback",
    });
    // Reporting 'solid' here would claim a fill that is not on the element.
    expect(bandStyleOf(bands()[0])).toBe("fallback");
  });
});

describe("CTA band: the live repo-landing-slug payload", () => {
  // Verbatim shape of GET /api/public/landings/repo-landing-slug: three
  // photographic banners, after_every placement. None of these edges passes
  // the flatness test, and all three bands paint anyway — the backend stopped
  // treating `*_edge_flat` as a suppressor.
  const LIVE: PublicLanding = {
    landing_id: 1,
    product_id: 4,
    product_name: "Landing Product",
    product_sku: "SKU-REPO-LANDING",
    product_price: 30,
    slug: "repo-landing-slug",
    banners: [
      makeBanner(58, 0, { top: "#817d7c", bottom: "#bba495" }),
      makeBanner(59, 1, { top: "#f6f7f9", bottom: "#0b377e" }),
      makeBanner(60, 2, { top: "#c8c3bb", bottom: "#c3beb9" }),
    ],
    cta_positions: [1, 2, 3],
    cta_backgrounds: [
      {
        position: 1,
        top_color: "#bba495",
        bottom_color: "#f6f7f9",
        blend_color: "#dbd3cf",
        foreground: "dark",
        source: "blend",
      },
      {
        position: 2,
        top_color: "#0b377e",
        bottom_color: "#c8c3bb",
        blend_color: "#9393a0",
        foreground: "dark",
        source: "blend",
      },
      {
        position: 3,
        top_color: "#c3beb9",
        bottom_color: "#c3beb9",
        blend_color: "#c3beb9",
        foreground: "dark",
        source: "above",
      },
    ],
    form_presentation: "inline",
    cta_band_style: "gradient",
  };

  it("renders a CTA after every banner, each on its own painted band", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(LIVE);
    renderAtSlug("repo-landing-slug");
    await screen.findByAltText("Banner 58");

    expect(screen.getAllByRole("button", { name: /Pedir ahora/i })).toHaveLength(3);
    expect(bands()).toHaveLength(3);

    expect(bandColors(bands()[0])).toMatchObject({ top: "#bba495", bottom: "#f6f7f9" });
    expect(bandColors(bands()[1])).toMatchObject({ top: "#0b377e", bottom: "#c8c3bb" });
    expect(bandColors(bands()[2])).toMatchObject({ top: "#c3beb9", bottom: "#c3beb9" });

    // Each band follows its own banner, in order.
    for (const bannerId of [58, 59, 60]) {
      expect(document.querySelector(`[data-banner-id="${bannerId}"]`)?.nextElementSibling)
        .toHaveClass("lp-page__cta-band");
    }
  });

  it("collapses every band to its blend color when the landing is set to solid", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue({ ...LIVE, cta_band_style: "solid" });
    renderAtSlug("repo-landing-slug");
    await screen.findByAltText("Banner 58");

    // Same payload, same colors — only the endpoints the page applies change.
    for (const [index, blend] of ["#dbd3cf", "#9393a0", "#c3beb9"].entries()) {
      const colors = bandColors(bands()[index]);
      expect(colors.top).toBe(blend);
      expect(colors.bottom).toBe(blend);
      expect(bandStyleOf(bands()[index])).toBe("solid");
    }
  });

  it("opens the pop-up form from a mid-page band CTA", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(LIVE);
    const user = userEvent.setup();
    renderAtSlug("repo-landing-slug");

    await user.click((await screen.findAllByRole("button", { name: /Pedir ahora/i }))[2]);

    expect(publicApi.recordCtaClick).toHaveBeenCalledWith("repo-landing-slug");
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByLabelText("Nombre completo")).toBeInTheDocument();
  });

  it("opens the same pop-up from the first band CTA regardless of form_presentation", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue({ ...LIVE, form_presentation: "modal" });
    const user = userEvent.setup();
    renderAtSlug("repo-landing-slug");

    await user.click((await screen.findAllByRole("button", { name: /Pedir ahora/i }))[0]);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByLabelText("Nombre completo")).toBeInTheDocument();
  });
});

describe("CTA band: the live draft-74 payload (painted bands)", () => {
  // Verbatim shape of GET /api/public/landings/draft-74, the one local landing
  // whose banner edges are flat enough to paint: two banners, after_every
  // placement, `blend` between them and `above` after the last.
  const LIVE_PAINTED: PublicLanding = {
    landing_id: 67,
    product_id: 74,
    product_name: "Producto Banner",
    product_sku: "SKU-UPLOAD-3",
    product_price: 10,
    slug: "draft-74",
    banners: [
      makeBanner(31, 0, { top: "#fe0002", bottom: "#fe0002" }),
      makeBanner(32, 1, { top: "#fe0002", bottom: "#fe0002" }),
    ],
    cta_positions: [1, 2],
    cta_backgrounds: [
      {
        position: 1,
        top_color: "#fe0002",
        bottom_color: "#fe0002",
        blend_color: "#fe0002",
        foreground: "dark",
        source: "blend",
      },
      {
        position: 2,
        top_color: "#fe0002",
        bottom_color: "#fe0002",
        blend_color: "#fe0002",
        foreground: "dark",
        source: "above",
      },
    ],
    form_presentation: "inline",
  };

  it("paints both bands from the banner edges and keeps the dark foreground", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(LIVE_PAINTED);
    renderAtSlug("draft-74");
    await screen.findByAltText("Banner 31");

    expect(bands()).toHaveLength(2);
    expect(bandColors(bands()[0])).toEqual({
      top: "#fe0002",
      bottom: "#fe0002",
      blend: "#fe0002",
      foreground: "dark",
      source: "blend",
    });
    expect(bandColors(bands()[1])).toMatchObject({
      top: "#fe0002",
      foreground: "dark",
      source: "above",
    });
  });

  it("attaches each painted band to its own banner", async () => {
    vi.mocked(publicApi.getLanding).mockResolvedValue(LIVE_PAINTED);
    renderAtSlug("draft-74");
    await screen.findByAltText("Banner 31");

    expect(document.querySelector('[data-banner-id="31"]')?.nextElementSibling).toHaveAttribute(
      "data-cta-source",
      "blend",
    );
    expect(document.querySelector('[data-banner-id="32"]')?.nextElementSibling).toHaveAttribute(
      "data-cta-source",
      "above",
    );
  });
});

describe("CTA band: mobile widths", () => {
  it.each([320, 360, 375])("renders the band and a full-width CTA at %ipx", async (width) => {
    window.innerWidth = width;
    vi.mocked(publicApi.getLanding).mockResolvedValue(makeLanding());

    renderAtSlug();
    await screen.findByAltText("Banner 1");

    // The band wraps the padded slot, so the gradient runs edge to edge while
    // the control keeps its gutter.
    const band = bands()[0];
    expect(band.firstElementChild).toHaveClass("lp-page__cta-slot");
    expect(band.querySelector(".cta-button")).toBeInTheDocument();
    // Nothing is absolutely positioned or negatively offset out of the band.
    expect(band.getAttribute("style") ?? "").not.toMatch(/position|margin|width/);
  });
});

describe("safeColor", () => {
  it("accepts #rgb and #rrggbb in either case", () => {
    expect(safeColor("#112233")).toBe("#112233");
    expect(safeColor("#AABBCC")).toBe("#AABBCC");
    expect(safeColor("#abc")).toBe("#abc");
    expect(safeColor("#FFF")).toBe("#FFF");
  });

  it("returns undefined for empty input", () => {
    expect(safeColor(null)).toBeUndefined();
    expect(safeColor(undefined)).toBeUndefined();
    expect(safeColor("")).toBeUndefined();
  });

  it("rejects every non-hex form, including CSS that would otherwise parse", () => {
    for (const value of [
      "red",
      "rgb(255,0,0)",
      "#gg0000",
      "#12345",
      "#1234567",
      "112233",
      "javascript:alert(1)",
      "url(evil)",
      "#fff; background: url(https://evil.example/x)",
      "var(--lp-action)",
      " #ffffff",
    ]) {
      expect(safeColor(value), value).toBeUndefined();
    }
  });
});
