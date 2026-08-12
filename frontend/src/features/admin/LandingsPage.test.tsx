import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LandingsPage } from "./LandingsPage";
import { landingsApi } from "../../api";
import type { LandingSummary } from "../../api";

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...actual,
    landingsApi: { list: vi.fn() },
  };
});

const DRAFT_LANDING: LandingSummary = {
  id: 1,
  product_id: 10,
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
  offers: [
    { quantity: 1, label: "1 unidad", sublabel: null, discount_percent: 0, compare_at_price: null },
    { quantity: 2, label: "2 unidades", sublabel: null, discount_percent: 0, compare_at_price: null },
    { quantity: 3, label: "3 unidades", sublabel: null, discount_percent: 0, compare_at_price: null },
  ],
  banner_count: 0,
  cta_text: null,
  cta_animation: null,
  cta_text_overrides: {},
  blocks_dark_mode: false,
};

const PUBLISHED_LANDING: LandingSummary = {
  ...DRAFT_LANDING,
  id: 2,
  product_id: 11,
  product_name: "Cargador solar",
  slug: "cargador-solar",
  status: "published",
  banner_count: 3,
};

describe("LandingsPage", () => {
  beforeEach(() => {
    vi.mocked(landingsApi.list).mockResolvedValue({
      landings: [DRAFT_LANDING, PUBLISHED_LANDING],
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  function renderPage() {
    return render(
      <MemoryRouter>
        <LandingsPage />
      </MemoryRouter>,
    );
  }

  it("lists landings with slug, banner count, and publication status", async () => {
    renderPage();

    expect(await screen.findByText("Audífonos inalámbricos")).toBeInTheDocument();
    expect(screen.getByText("/p/cargador-solar")).toBeInTheDocument();
    expect(screen.getByText("Borrador")).toBeInTheDocument();
    expect(screen.getByText("Publicado")).toBeInTheDocument();
  });

  it("links each landing to its editor", async () => {
    renderPage();

    const links = await screen.findAllByRole("link", { name: "Gestionar" });
    expect(links[0]).toHaveAttribute("href", "/admin/landings/1");
  });

  it("only links to the public page when the landing is published and the product active", async () => {
    renderPage();
    await screen.findByText("Audífonos inalámbricos");

    const publicLinks = screen.getAllByRole("link", { name: "Ver pública" });
    expect(publicLinks).toHaveLength(1);
    expect(publicLinks[0]).toHaveAttribute("href", "/p/cargador-solar");
    expect(screen.getByRole("button", { name: "Ver pública" })).toBeDisabled();
  });

  it("reports a load failure without rendering rows", async () => {
    vi.mocked(landingsApi.list).mockRejectedValue(new Error("boom"));
    renderPage();

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "No se pudieron cargar las landings.",
      ),
    );
  });
});
