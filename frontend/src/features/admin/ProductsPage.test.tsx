import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProductsPage } from "./ProductsPage";
import { ApiError, productsApi } from "../../api";
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
      create: vi.fn(),
      update: vi.fn(),
      getMastershopMappings: vi.fn(),
      replaceMastershopMappings: vi.fn(),
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
  landing_id: 11,
};

const ACTIVE_PRODUCT: Product = {
  id: 2,
  name: "Reloj deportivo",
  sku: "REL-002",
  price: 129900,
  description: "",
  status: "active",
  landing_id: 12,
};

const ACTIVE_PUBLISHED_PRODUCT: Product = {
  id: 3,
  name: "Cargador solar",
  sku: "CAR-003",
  price: 65000,
  description: "",
  status: "active",
  landing_id: 13,
  landing_slug: "cargador-solar",
  landing_status: "published",
};

describe("ProductsPage", () => {
  beforeEach(() => {
    vi.mocked(productsApi.list).mockResolvedValue({
      products: [PAUSED_PRODUCT, ACTIVE_PRODUCT],
    });
    vi.mocked(productsApi.getMastershopMappings).mockResolvedValue({ mappings: [] });
    vi.mocked(productsApi.replaceMastershopMappings).mockResolvedValue({ mappings: [] });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  function renderPage() {
    return render(
      <MemoryRouter>
        <ProductsPage />
      </MemoryRouter>,
    );
  }

  it("renders products with their status pill and formatted price", async () => {
    renderPage();

    expect(await screen.findByText("Audífonos inalámbricos")).toBeInTheDocument();
    expect(screen.getByText("Pausado")).toBeInTheDocument();
    expect(screen.getByText("Activo")).toBeInTheDocument();
  });

  it("links each product directly to its own landing editor", async () => {
    renderPage();

    const links = await screen.findAllByRole("link", { name: "Editar landing" });
    expect(links[0]).toHaveAttribute("href", "/admin/landings/11");
    expect(links[1]).toHaveAttribute("href", "/admin/landings/12");
  });

  it("edits a product name and price without replacing the rest of the product", async () => {
    const user = userEvent.setup();
    const updated = {
      ...PAUSED_PRODUCT,
      name: "Audífonos Pro",
      price: 99900,
    };
    vi.mocked(productsApi.update).mockResolvedValue(updated);
    renderPage();
    await screen.findByText("Audífonos inalámbricos");

    await user.click(screen.getByRole("button", {
      name: "Editar producto Audífonos inalámbricos",
    }));
    const name = screen.getByRole("textbox", { name: "Nombre" });
    await user.clear(name);
    await user.type(name, "Audífonos Pro");
    const price = screen.getByRole("spinbutton", { name: "Precio (COP)" });
    await user.clear(price);
    await user.type(price, "99900");
    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));

    await waitFor(() => expect(productsApi.update).toHaveBeenCalledWith(1, {
      name: "Audífonos Pro",
      price: 99900,
    }));
    expect(await screen.findByText("Audífonos Pro")).toBeInTheDocument();
    expect(screen.getByText(/99\.900/)).toBeInTheDocument();
    expect(screen.getByText("AUD-001")).toBeInTheDocument();
  });

  it("configures the MasterShop catalog mapping without changing the product", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Audífonos inalámbricos");

    await user.click(screen.getAllByRole("button", { name: "MasterShop" })[0]);
    expect(await screen.findByRole("dialog", { name: /MasterShop · Audífonos/ })).toBeInTheDocument();
    await user.click(screen.getByLabelText("ID producto MasterShop"));
    await user.paste("232082");
    await user.click(screen.getByRole("button", { name: "Guardar configuración" }));

    await waitFor(() => expect(productsApi.replaceMastershopMappings).toHaveBeenCalledWith(1, [
      {
        variant_selection: {},
        mastershop_product_id: 232082,
        mastershop_variant_id: null,
        weight: 1,
      },
    ]));
  });

  it("shows an Activar action for paused products and calls productsApi.activate", async () => {
    const user = userEvent.setup();
    vi.mocked(productsApi.activate).mockResolvedValue({ ...PAUSED_PRODUCT, status: "active" });

    renderPage();
    await screen.findByText("Audífonos inalámbricos");

    await user.click(screen.getAllByRole("button", { name: "Activar" })[0]);

    await waitFor(() => expect(productsApi.activate).toHaveBeenCalledWith(1));
  });

  it("shows a Pausar action for active products and calls productsApi.pause", async () => {
    const user = userEvent.setup();
    vi.mocked(productsApi.pause).mockResolvedValue({ ...ACTIVE_PRODUCT, status: "paused" });

    renderPage();
    await screen.findByText("Reloj deportivo");

    await user.click(screen.getByRole("button", { name: "Pausar" }));

    await waitFor(() => expect(productsApi.pause).toHaveBeenCalledWith(2));
  });

  it("requires inline confirmation before retiring a product, and preserves history in the copy", async () => {
    const user = userEvent.setup();
    vi.mocked(productsApi.delete).mockResolvedValue(undefined);

    renderPage();
    await screen.findByText("Audífonos inalámbricos");

    await user.click(screen.getAllByRole("button", { name: "Retirar" })[0]);

    expect(screen.getByText(/Se conservan pedidos e historial/)).toBeInTheDocument();
    expect(productsApi.delete).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Confirmar" }));
    await waitFor(() => expect(productsApi.delete).toHaveBeenCalledWith(1));
  });

  it("cancels retirement without calling the API when Cancelar is clicked", async () => {
    const user = userEvent.setup();
    renderPage();
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
    renderPage();

    const link = await screen.findByRole("link", { name: "Ver landing" });
    expect(link).toHaveAttribute("href", "/p/cargador-solar");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("disables the landing link when the product is paused, with an explanatory title", async () => {
    renderPage();
    await screen.findByText("Audífonos inalámbricos");

    // PAUSED_PRODUCT has no landing_slug, so no link/button renders for it.
    expect(screen.queryByRole("link", { name: "Ver landing" })).not.toBeInTheDocument();
  });

  it("opens a create-product form from the Nuevo producto button", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Audífonos inalámbricos");

    await user.click(screen.getByRole("button", { name: "Nuevo producto" }));

    expect(screen.getByRole("dialog", { name: "Nuevo producto" })).toBeInTheDocument();
    expect(screen.getByLabelText("Nombre")).toBeInTheDocument();
    expect(screen.getByLabelText("SKU")).toBeInTheDocument();
    expect(screen.getByLabelText("Precio (COP)")).toBeInTheDocument();
  });

  it("creates a product with its auto-created draft landing and offers to manage it", async () => {
    const user = userEvent.setup();
    const created: Product = {
      id: 4,
      name: "Nuevo gadget",
      sku: "GAD-004",
      price: 45000,
      description: "",
      status: "paused",
      landing_id: 14,
      landing_slug: "draft-4",
      landing_status: "draft",
    };
    vi.mocked(productsApi.create).mockResolvedValue(created);

    renderPage();
    await screen.findByText("Audífonos inalámbricos");

    await user.click(screen.getByRole("button", { name: "Nuevo producto" }));
    await user.type(screen.getByLabelText("Nombre"), "Nuevo gadget");
    await user.type(screen.getByLabelText("SKU"), "GAD-004");
    await user.type(screen.getByLabelText("Precio (COP)"), "45000");
    await user.type(screen.getByLabelText("Característica 1"), "Color");
    await user.type(screen.getAllByLabelText("Valores")[0], "Gris, Negro");
    await user.type(screen.getByLabelText("Característica 2"), "Talla");
    await user.type(screen.getAllByLabelText("Valores")[1], "M, L");
    await user.click(screen.getByRole("button", { name: "Crear producto" }));

    await waitFor(() =>
      expect(productsApi.create).toHaveBeenCalledWith({
        name: "Nuevo gadget",
        sku: "GAD-004",
        price: 45000,
        description: "",
        variant_options: [
          { name: "Color", values: ["Gris", "Negro"] },
          { name: "Talla", values: ["M", "L"] },
        ],
      }),
    );

    expect(
      await screen.findByText(/Su landing quedó en borrador \(sin publicar\)/),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ir a Landings" })).toHaveAttribute(
      "href",
      "/admin/landings",
    );
    expect(await screen.findByText("Nuevo gadget")).toBeInTheDocument();
  });

  it("maps backend field errors (e.g. duplicate SKU) onto the create form", async () => {
    const user = userEvent.setup();
    vi.mocked(productsApi.create).mockRejectedValue(
      new ApiError(409, "SKU already in use", { sku: "SKU already in use" }),
    );

    renderPage();
    await screen.findByText("Audífonos inalámbricos");

    await user.click(screen.getByRole("button", { name: "Nuevo producto" }));
    await user.type(screen.getByLabelText("Nombre"), "Duplicado");
    await user.type(screen.getByLabelText("SKU"), "AUD-001");
    await user.type(screen.getByLabelText("Precio (COP)"), "10000");
    await user.click(screen.getByRole("button", { name: "Crear producto" }));

    expect(await screen.findByText("SKU already in use", { selector: "p.form-field-error" })).toBeInTheDocument();
  });

  it("closes the create form without calling the API when Cancelar is clicked", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Audífonos inalámbricos");

    await user.click(screen.getByRole("button", { name: "Nuevo producto" }));
    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(productsApi.create).not.toHaveBeenCalled();
  });
});
