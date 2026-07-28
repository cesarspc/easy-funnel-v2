import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProductsPage } from "./ProductsPage";
import { productsApi } from "../../api";
import type { Product } from "../../api";

vi.mock("../../api", async () => {
  const actual = await vi.importActual<typeof import("../../api")>("../../api");
  return {
    ...actual,
    productsApi: {
      list: vi.fn(),
      activate: vi.fn(),
      pause: vi.fn(),
      delete: vi.fn(),
    },
  };
});

const PAUSED_PRODUCT: Product = {
  id: 1,
  name: "Audífonos inalámbricos",
  sku: "AUD-001",
  price: 89900,
  description: "",
  status: "paused",
};

const ACTIVE_PRODUCT: Product = {
  id: 2,
  name: "Reloj deportivo",
  sku: "REL-002",
  price: 129900,
  description: "",
  status: "active",
};

const ACTIVE_PUBLISHED_PRODUCT: Product = {
  id: 3,
  name: "Cargador solar",
  sku: "CAR-003",
  price: 65000,
  description: "",
  status: "active",
  landing_slug: "cargador-solar",
  landing_status: "published",
};

describe("ProductsPage", () => {
  beforeEach(() => {
    vi.mocked(productsApi.list).mockResolvedValue({
      products: [PAUSED_PRODUCT, ACTIVE_PRODUCT],
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders products with their status pill and formatted price", async () => {
    render(<ProductsPage />);

    expect(await screen.findByText("Audífonos inalámbricos")).toBeInTheDocument();
    expect(screen.getByText("Pausado")).toBeInTheDocument();
    expect(screen.getByText("Activo")).toBeInTheDocument();
  });

  it("shows an Activar action for paused products and calls productsApi.activate", async () => {
    const user = userEvent.setup();
    vi.mocked(productsApi.activate).mockResolvedValue({ ...PAUSED_PRODUCT, status: "active" });

    render(<ProductsPage />);
    await screen.findByText("Audífonos inalámbricos");

    await user.click(screen.getAllByRole("button", { name: "Activar" })[0]);

    await waitFor(() => expect(productsApi.activate).toHaveBeenCalledWith(1));
  });

  it("shows a Pausar action for active products and calls productsApi.pause", async () => {
    const user = userEvent.setup();
    vi.mocked(productsApi.pause).mockResolvedValue({ ...ACTIVE_PRODUCT, status: "paused" });

    render(<ProductsPage />);
    await screen.findByText("Reloj deportivo");

    await user.click(screen.getByRole("button", { name: "Pausar" }));

    await waitFor(() => expect(productsApi.pause).toHaveBeenCalledWith(2));
  });

  it("requires inline confirmation before retiring a product, and preserves history in the copy", async () => {
    const user = userEvent.setup();
    vi.mocked(productsApi.delete).mockResolvedValue(undefined);

    render(<ProductsPage />);
    await screen.findByText("Audífonos inalámbricos");

    await user.click(screen.getAllByRole("button", { name: "Retirar" })[0]);

    expect(screen.getByText(/Se conservan pedidos e historial/)).toBeInTheDocument();
    expect(productsApi.delete).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Confirmar" }));
    await waitFor(() => expect(productsApi.delete).toHaveBeenCalledWith(1));
  });

  it("cancels retirement without calling the API when Cancelar is clicked", async () => {
    const user = userEvent.setup();
    render(<ProductsPage />);
    await screen.findByText("Audífonos inalámbricos");

    await user.click(screen.getAllByRole("button", { name: "Retirar" })[0]);
    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(productsApi.delete).not.toHaveBeenCalled();
    expect(screen.getAllByRole("button", { name: "Retirar" })[0]).toBeInTheDocument();
  });

  it("links to the public landing when the product is active and its landing is published", async () => {
    vi.mocked(productsApi.list).mockResolvedValue({
      products: [ACTIVE_PUBLISHED_PRODUCT],
    });
    render(<ProductsPage />);

    const link = await screen.findByRole("link", { name: "Ver landing" });
    expect(link).toHaveAttribute("href", "/p/cargador-solar");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("disables the landing link when the product is paused, with an explanatory title", async () => {
    render(<ProductsPage />);
    await screen.findByText("Audífonos inalámbricos");

    // PAUSED_PRODUCT has no landing_slug, so no link/button renders for it.
    expect(screen.queryByRole("link", { name: "Ver landing" })).not.toBeInTheDocument();
  });
});
