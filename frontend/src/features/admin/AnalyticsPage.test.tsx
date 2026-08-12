import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AnalyticsPage } from "./AnalyticsPage";
import { analyticsApi, ApiError, landingsApi } from "../../api";
import type { FraudAnalytics, LandingAnalytics, LandingSummary, OrdersPerDay } from "../../api";

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...actual,
    analyticsApi: {
      getOrdersPerDay: vi.fn(),
      getLandingAnalytics: vi.fn(),
      getFraudAnalytics: vi.fn(),
    },
    landingsApi: {
      list: vi.fn(),
    },
  };
});

const ORDERS_PER_DAY: OrdersPerDay[] = [
  { date: "2026-02-02", count: 5 },
  { date: "2026-02-01", count: 3 },
];

const LANDING_SUMMARY: LandingSummary = {
  id: 7,
  product_id: 3,
  product_name: "Audífonos inalámbricos",
  product_sku: "AUD-001",
  product_status: "active",
  slug: "audifonos-inalambricos",
  status: "published",
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
  banner_count: 2,
  cta_text: null,
  cta_animation: null,
  cta_text_overrides: {},
  blocks_dark_mode: false,
};

const LANDING_ANALYTICS: LandingAnalytics[] = [
  { landing_id: 7, views: 200, clicks: 40, orders: 10, conversion_rate: 0.05 },
];

const FRAUD_ANALYTICS: FraudAnalytics[] = [
  { date: "2026-02-02", flagged_orders: 2, total_orders: 8, flagged_fraud_rate: 0.25 },
  { date: "2026-02-01", flagged_orders: 0, total_orders: 3, flagged_fraud_rate: 0 },
];

function mockSuccess() {
  vi.mocked(analyticsApi.getOrdersPerDay).mockResolvedValue(ORDERS_PER_DAY);
  vi.mocked(analyticsApi.getLandingAnalytics).mockResolvedValue(LANDING_ANALYTICS);
  vi.mocked(analyticsApi.getFraudAnalytics).mockResolvedValue(FRAUD_ANALYTICS);
  vi.mocked(landingsApi.list).mockResolvedValue({ landings: [LANDING_SUMMARY] });
}

describe("AnalyticsPage", () => {
  beforeEach(() => {
    mockSuccess();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("loads all three analytics queries for the default 30-day range on mount", async () => {
    render(<AnalyticsPage />);

    await waitFor(() => expect(analyticsApi.getOrdersPerDay).toHaveBeenCalled());
    expect(analyticsApi.getLandingAnalytics).toHaveBeenCalled();
    expect(analyticsApi.getFraudAnalytics).toHaveBeenCalled();
    expect(landingsApi.list).toHaveBeenCalledWith(true);
  });

  it("renders orders-per-day rows newest first without recomputing the count", async () => {
    render(<AnalyticsPage />);

    const rows = await screen.findAllByRole("row");
    // Header + 2026-02-02 first, then 2026-02-01 (newest first).
    expect(rows[1]).toHaveTextContent("2026-02-02");
    expect(rows[1]).toHaveTextContent("5");
    expect(rows[2]).toHaveTextContent("2026-02-01");
  });

  it("joins landing analytics with the landing's product name and slug", async () => {
    render(<AnalyticsPage />);

    expect(await screen.findByText("Audífonos inalámbricos")).toBeInTheDocument();
    expect(screen.getByText("/p/audifonos-inalambricos")).toBeInTheDocument();
  });

  it("renders conversion_rate and flagged_fraud_rate as percentages without client-side recomputation", async () => {
    render(<AnalyticsPage />);

    expect(await screen.findByText("5,0%")).toBeInTheDocument(); // conversion_rate 0.05
    expect(screen.getAllByText("25,0%").length).toBeGreaterThan(0); // flagged_fraud_rate 0.25
  });

  it("shows a zero fraud rate day without special-casing it", async () => {
    render(<AnalyticsPage />);

    await screen.findAllByText("25,0%");
    expect(screen.getAllByText("0,0%").length).toBeGreaterThan(0);
  });

  it("re-queries with the new range when the date form is submitted", async () => {
    const user = userEvent.setup();
    render(<AnalyticsPage />);
    await waitFor(() => expect(analyticsApi.getOrdersPerDay).toHaveBeenCalledTimes(1));

    const dateFrom = screen.getByLabelText("Desde");
    await user.clear(dateFrom);
    await user.type(dateFrom, "2026-01-01");
    await user.click(screen.getByRole("button", { name: "Aplicar" }));

    await waitFor(() =>
      expect(analyticsApi.getOrdersPerDay).toHaveBeenLastCalledWith("2026-01-01", expect.any(String)),
    );
  });

  it("binds an inverted-range rejection to the date_from control", async () => {
    vi.mocked(analyticsApi.getOrdersPerDay).mockRejectedValue(
      new ApiError(422, "The start of the range must not be after its end.", {
        date_from: "The start of the range must not be after its end.",
      }),
    );
    render(<AnalyticsPage />);

    const dateFromInput = await screen.findByLabelText("Desde");
    await waitFor(() => expect(dateFromInput).toHaveAttribute("aria-invalid", "true"));
    expect(dateFromInput).toHaveAccessibleDescription(
      "The start of the range must not be after its end.",
    );
  });

  it("shows an empty-state message when a query returns no rows for the range", async () => {
    vi.mocked(analyticsApi.getOrdersPerDay).mockResolvedValue([]);
    vi.mocked(analyticsApi.getFraudAnalytics).mockResolvedValue([]);
    vi.mocked(analyticsApi.getLandingAnalytics).mockResolvedValue([]);
    render(<AnalyticsPage />);

    expect(
      await screen.findAllByText("No hay pedidos en el rango seleccionado."),
    ).not.toHaveLength(0);
    expect(
      screen.getByText("No hay datos de landings en el rango seleccionado."),
    ).toBeInTheDocument();
  });

  it("falls back to the landing id when no matching landing summary is found", async () => {
    vi.mocked(landingsApi.list).mockResolvedValue({ landings: [] });
    render(<AnalyticsPage />);

    expect(await screen.findByText("Landing #7")).toBeInTheDocument();
  });
});
