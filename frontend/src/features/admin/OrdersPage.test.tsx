import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OrdersPage } from "./OrdersPage";
import { ordersApi } from "../../api";
import type { Order } from "../../api";

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...actual,
    ordersApi: {
      list: vi.fn(),
      get: vi.fn(),
      export: vi.fn(),
      updateFulfillment: vi.fn(),
      retryMastershop: vi.fn(),
    },
  };
});

const SAMPLE_ORDER: Order = {
  id: 101,
  product_id: 1,
  landing_id: 1,
  landing_slug: "producto-ejemplo",
  customer_name: "María Gómez",
  phone_e164: "+573001234567",
  department: "Antioquia",
  city: "Medellín",
  address: "Calle 10 #20-30",
  quantity: 2,
  unit_price: 59900,
  discount_percent: 10,
  total_price: 107820,
  status: "pending",
  ip_address: "203.0.113.5",
  user_agent: "test-agent",
  created_at: "2026-01-15T10:00:00Z",
  updated_at: "2026-01-15T10:00:00Z",
  fulfillment_details: {
    first_name: "María",
    last_name: "Gómez",
    address1: "Calle 10 #20-30",
    address2: null,
  },
  mastershop_sync: {
    status: "failed",
    attempt_count: 1,
    response_status: 422,
    response_body: { message: "invalid variant" },
    last_error: "MasterShop returned HTTP 422.",
    last_attempt_at: "2026-01-15T10:01:00Z",
    synced_at: null,
    updated_at: "2026-01-15T10:01:00Z",
  },
};

describe("OrdersPage", () => {
  beforeEach(() => {
    vi.mocked(ordersApi.list).mockResolvedValue({ orders: [SAMPLE_ORDER], count: 1 });
    vi.mocked(ordersApi.get).mockResolvedValue({
      ...SAMPLE_ORDER,
      product_name: "Producto ejemplo",
      product_sku: "SKU-001",
      variant_selections: [{ Color: "Gris" }, { Color: "Negro" }],
      fraud_flags: [],
    });
    vi.mocked(ordersApi.export).mockResolvedValue(new Blob(["csv"], { type: "text/csv" }));
    vi.mocked(ordersApi.updateFulfillment).mockResolvedValue(SAMPLE_ORDER);
    vi.mocked(ordersApi.retryMastershop).mockResolvedValue({
      order_id: SAMPLE_ORDER.id,
      mastershop_sync: { ...SAMPLE_ORDER.mastershop_sync!, status: "success", response_status: 200 },
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders orders with their status pill", async () => {
    render(<OrdersPage />);

    expect(await screen.findByText("María Gómez")).toBeInTheDocument();
    const pill = screen.getByText("Pendiente", { selector: ".status-pill" });
    expect(pill).toBeInTheDocument();
  });

  it("shows an empty state when no orders match the filters", async () => {
    vi.mocked(ordersApi.list).mockResolvedValue({ orders: [], count: 0 });
    render(<OrdersPage />);

    expect(
      await screen.findByText("No hay pedidos que coincidan con los filtros actuales."),
    ).toBeInTheDocument();
  });

  it("re-fetches with the selected status filter", async () => {
    const user = userEvent.setup();
    render(<OrdersPage />);
    await screen.findByText("María Gómez");

    await user.selectOptions(screen.getByLabelText("Estado"), "confirmed");

    await waitFor(() =>
      expect(ordersApi.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ status: "confirmed" }),
      ),
    );
  });

  it("triggers a CSV export using the active filters", async () => {
    const user = userEvent.setup();
    const createObjectURL = vi.fn().mockReturnValue("blob:mock");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL });

    render(<OrdersPage />);
    await screen.findByText("María Gómez");

    await user.click(screen.getByRole("button", { name: /Exportar CSV/i }));

    await waitFor(() => expect(ordersApi.export).toHaveBeenCalled());
    expect(createObjectURL).toHaveBeenCalled();
  });

  it("opens every order detail from the eye action", async () => {
    const user = userEvent.setup();
    render(<OrdersPage />);
    await screen.findByText("María Gómez");

    await user.click(screen.getByRole("button", { name: /todos los detalles.*#101/i }));

    expect(await screen.findByRole("dialog", { name: "Pedido #101" })).toBeInTheDocument();
    expect(ordersApi.get).toHaveBeenCalledWith(101);
    expect(screen.getByText(/107\.820/)).toBeInTheDocument();
    expect(screen.getByText("Producto ejemplo")).toBeInTheDocument();
    expect(screen.getByText("Color: Gris")).toBeInTheDocument();
    expect(screen.getByText("Sin alertas de fraude.")).toBeInTheDocument();
    expect(screen.getByText("203.0.113.5")).toBeInTheDocument();
    expect(screen.getByText("MasterShop returned HTTP 422.")).toBeInTheDocument();
  });

  it("edits failed fulfillment data and retries MasterShop synchronization", async () => {
    const user = userEvent.setup();
    render(<OrdersPage />);
    await screen.findByText("María Gómez");
    await user.click(screen.getByRole("button", { name: /todos los detalles.*#101/i }));
    await screen.findByRole("dialog", { name: "Pedido #101" });

    await user.clear(screen.getByLabelText("Dirección 2"));
    await user.type(screen.getByLabelText("Dirección 2"), "Apto 201");
    await user.click(screen.getByRole("button", { name: "Guardar datos de entrega" }));
    await waitFor(() => expect(ordersApi.updateFulfillment).toHaveBeenCalledWith(101,
      expect.objectContaining({ first_name: "María", last_name: "Gómez", address2: "Apto 201" }),
    ));

    await user.click(screen.getByRole("button", { name: "Reintentar sincronización" }));
    await waitFor(() => expect(ordersApi.retryMastershop).toHaveBeenCalledWith(101));
  });
});
