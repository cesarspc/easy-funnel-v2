/**
 * Products list (Requirement 8.1-8.2). Activate/pause toggle availability
 * without deleting data; retire applies Soft_Deletion and is confirmed
 * explicitly, naming it as retirement with historical data preserved
 * (Requirement 2.13, 8.2).
 *
 * "Nuevo producto" opens a form that calls `productsApi.create`. The backend
 * creates the Product and its single draft Landing atomically
 * (`ProductLifecycleService.create_product`), so every new product already
 * has an unpublished landing ready to manage from the Landings list — the
 * dashboard never has to create the landing as a second step.
 */

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Modal } from "../../components/Modal";
import { FormField } from "../../components/FormField";
import { StatusPill } from "../../components";
import type { Product } from "../../api";
import { ApiError, productsApi } from "../../api";
import "./ProductsPage.css";

const CURRENCY_FORMATTER = new Intl.NumberFormat("es-CO", {
  style: "currency",
  currency: "COP",
  maximumFractionDigits: 0,
});

interface CreateFormValues {
  name: string;
  sku: string;
  price: string;
  description: string;
  variantOptions: { name: string; values: string }[];
}

const EMPTY_CREATE_FORM: CreateFormValues = {
  name: "",
  sku: "",
  price: "",
  description: "",
  variantOptions: [
    { name: "", values: "" },
    { name: "", values: "" },
  ],
};

export function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [confirmRetireId, setConfirmRetireId] = useState<number | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState<CreateFormValues>(EMPTY_CREATE_FORM);
  const [createFieldErrors, setCreateFieldErrors] = useState<Record<string, string>>({});
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [createdLandingSlug, setCreatedLandingSlug] = useState<string | null>(null);

  function load() {
    setLoading(true);
    setError(null);
    productsApi
      .list()
      .then((response) => setProducts(response.products))
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "No se pudieron cargar los productos.");
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
  }, []);

  function openCreateModal() {
    setCreateForm(EMPTY_CREATE_FORM);
    setCreateFieldErrors({});
    setCreateError(null);
    setCreatedLandingSlug(null);
    setCreateOpen(true);
  }

  function closeCreateModal() {
    setCreateOpen(false);
  }
  const handleModalClose = useCallback(() => setCreateOpen(false), []);

  async function handleCreateSubmit(event: FormEvent) {
    event.preventDefault();
    setCreateError(null);
    setCreateFieldErrors({});

    const price = Number(createForm.price);
    if (!Number.isFinite(price)) {
      setCreateFieldErrors({ price: "Ingresa un precio válido." });
      return;
    }

    setCreating(true);
    try {
      const created = await productsApi.create({
        name: createForm.name,
        sku: createForm.sku,
        price,
        description: createForm.description,
        variant_options: createForm.variantOptions
          .filter((option) => option.name.trim() || option.values.trim())
          .map((option) => ({
            name: option.name.trim(),
            values: option.values.split(",").map((value) => value.trim()).filter(Boolean),
          })),
      });
      setProducts((list) => [...list, created]);
      // The backend created a draft (unpublished) landing atomically; surface
      // it so the merchant can jump straight to "Gestionar" from here too.
      setCreatedLandingSlug(created.landing_slug ?? null);
      setCreateForm(EMPTY_CREATE_FORM);
    } catch (err) {
      if (err instanceof ApiError) {
        setCreateError(err.message);
        if (err.fieldErrors) setCreateFieldErrors(err.fieldErrors);
      } else {
        setCreateError("No se pudo crear el producto.");
      }
    } finally {
      setCreating(false);
    }
  }

  async function handleActivate(id: number) {
    setPendingId(id);
    try {
      const updated = await productsApi.activate(id);
      setProducts((list) => list.map((p) => (p.id === id ? updated : p)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo activar el producto.");
    } finally {
      setPendingId(null);
    }
  }

  async function handlePause(id: number) {
    setPendingId(id);
    try {
      const updated = await productsApi.pause(id);
      setProducts((list) => list.map((p) => (p.id === id ? updated : p)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo pausar el producto.");
    } finally {
      setPendingId(null);
    }
  }

  async function handleRetire(id: number) {
    setPendingId(id);
    try {
      await productsApi.delete(id);
      setProducts((list) => list.filter((p) => p.id !== id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo retirar el producto.");
    } finally {
      setPendingId(null);
      setConfirmRetireId(null);
    }
  }

  return (
    <div className="products-page">
      <div className="products-page__header">
        <h1 className="products-page__title">Productos</h1>
        <button
          type="button"
          className="products-page__new-button"
          onClick={openCreateModal}
        >
          Nuevo producto
        </button>
      </div>

      {error && (
        <p className="products-page__error" role="alert">
          {error}
        </p>
      )}

      {createOpen && (
        <Modal
          isOpen={createOpen}
          onClose={handleModalClose}
          title="Nuevo producto"
          subtitle="Se crea con una landing en blanco, sin publicar, lista para editar."
        >
          {createdLandingSlug !== null ? (
            <div className="products-page__create-success">
              <p role="status">
                Producto creado. Su landing quedó en borrador (sin publicar).
              </p>
              <div className="products-page__create-success-actions">
                <Link
                  className="products-table__action products-table__action--primary"
                  to="/admin/landings"
                  onClick={closeCreateModal}
                >
                  Ir a Landings
                </Link>
                <button type="button" className="products-table__action" onClick={closeCreateModal}>
                  Cerrar
                </button>
              </div>
            </div>
          ) : (
            <form className="products-page__create-form" onSubmit={handleCreateSubmit} noValidate>
              {createError && (
                <p className="products-page__error" role="alert">
                  {createError}
                </p>
              )}

              <FormField
                name="name"
                label="Nombre"
                value={createForm.name}
                onChange={(e) => setCreateForm((f) => ({ ...f, name: e.target.value }))}
                error={createFieldErrors.name}
                required
                autoComplete="off"
              />

              <FormField
                name="sku"
                label="SKU"
                value={createForm.sku}
                onChange={(e) => setCreateForm((f) => ({ ...f, sku: e.target.value }))}
                error={createFieldErrors.sku}
                required
                autoComplete="off"
              />

              <FormField
                name="price"
                label="Precio (COP)"
                type="number"
                inputMode="numeric"
                min={0}
                step={1}
                value={createForm.price}
                onChange={(e) => setCreateForm((f) => ({ ...f, price: e.target.value }))}
                error={createFieldErrors.price}
                required
              />

              <FormField
                name="description"
                label="Descripción"
                textarea
                value={createForm.description}
                onChange={(e) => setCreateForm((f) => ({ ...f, description: e.target.value }))}
                error={createFieldErrors.description}
              />

              <fieldset className="products-page__variants">
                <legend>Variantes (opcional, máximo 2)</legend>
                <p>Define el nombre y sus valores separados por comas. No se podrán agregar después.</p>
                {createForm.variantOptions.map((option, index) => (
                  <div className="products-page__variant-row" key={index}>
                    <FormField
                      name={`variant-name-${index}`}
                      label={`Característica ${index + 1}`}
                      placeholder={index === 0 ? "Color" : "Talla"}
                      value={option.name}
                      onChange={(event) =>
                        setCreateForm((form) => ({
                          ...form,
                          variantOptions: form.variantOptions.map((item, itemIndex) =>
                            itemIndex === index ? { ...item, name: event.target.value } : item,
                          ),
                        }))
                      }
                      autoComplete="off"
                    />
                    <FormField
                      name={`variant-values-${index}`}
                      label="Valores"
                      placeholder={index === 0 ? "Gris, Negro" : "S, M, L"}
                      value={option.values}
                      onChange={(event) =>
                        setCreateForm((form) => ({
                          ...form,
                          variantOptions: form.variantOptions.map((item, itemIndex) =>
                            itemIndex === index ? { ...item, values: event.target.value } : item,
                          ),
                        }))
                      }
                      autoComplete="off"
                    />
                  </div>
                ))}
                {createFieldErrors.variant_options && (
                  <p className="products-page__error" role="alert">
                    {createFieldErrors.variant_options}
                  </p>
                )}
              </fieldset>

              <div className="products-page__create-form-actions">
                <button
                  type="button"
                  className="products-table__action"
                  onClick={closeCreateModal}
                  disabled={creating}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="products-table__action products-table__action--primary"
                  disabled={creating}
                >
                  {creating ? "Creando…" : "Crear producto"}
                </button>
              </div>
            </form>
          )}
        </Modal>
      )}

      <div className="products-page__table-wrap">
        <table className="products-table">
          <thead>
            <tr>
              <th>Producto</th>
              <th>SKU</th>
              <th>Precio</th>
              <th>Estado</th>
              <th>
                <span className="sr-only">Acciones</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} className="products-table__empty">
                  Cargando productos…
                </td>
              </tr>
            ) : products.length === 0 ? (
              <tr>
                <td colSpan={5} className="products-table__empty">
                  Todavía no hay productos. Crea el primero para empezar a vender.
                </td>
              </tr>
            ) : (
              products.map((product) => (
                <tr key={product.id}>
                  <td>{product.name}</td>
                  <td className="products-table__data">{product.sku}</td>
                  <td className="products-table__data">
                    {CURRENCY_FORMATTER.format(product.price)}
                  </td>
                  <td>
                    <StatusPill status={product.status} />
                  </td>
                  <td className="products-table__actions">
                    {confirmRetireId === product.id ? (
                      <span className="products-table__confirm">
                        <span className="products-table__confirm-text">
                          ¿Retirar? Se conservan pedidos e historial.
                        </span>
                        <button
                          type="button"
                          className="products-table__action products-table__action--danger"
                          disabled={pendingId === product.id}
                          onClick={() => void handleRetire(product.id)}
                        >
                          Confirmar
                        </button>
                        <button
                          type="button"
                          className="products-table__action"
                          onClick={() => setConfirmRetireId(null)}
                        >
                          Cancelar
                        </button>
                      </span>
                    ) : (
                      <span className="products-table__actions-row">
                        {product.landing_id && (
                          <Link
                            className="products-table__action products-table__action--primary"
                            to={`/admin/landings/${product.landing_id}`}
                          >
                            Editar landing
                          </Link>
                        )}
                        {product.landing_slug &&
                          (product.status === "active" &&
                          product.landing_status === "published" ? (
                            <a
                              href={`/p/${product.landing_slug}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="products-table__action"
                            >
                              Ver landing
                            </a>
                          ) : (
                            <button
                              type="button"
                              className="products-table__action"
                              disabled
                              title="La landing solo es visible cuando el producto está activo y la landing publicada."
                            >
                              Ver landing
                            </button>
                          ))}
                        {product.status === "paused" && (
                          <button
                            type="button"
                            className="products-table__action products-table__action--primary"
                            disabled={pendingId === product.id}
                            onClick={() => void handleActivate(product.id)}
                          >
                            Activar
                          </button>
                        )}
                        {product.status === "active" && (
                          <button
                            type="button"
                            className="products-table__action"
                            disabled={pendingId === product.id}
                            onClick={() => void handlePause(product.id)}
                          >
                            Pausar
                          </button>
                        )}
                        {product.status !== "retired" && (
                          <button
                            type="button"
                            className="products-table__action"
                            disabled={pendingId === product.id}
                            onClick={() => setConfirmRetireId(product.id)}
                          >
                            Retirar
                          </button>
                        )}
                      </span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
