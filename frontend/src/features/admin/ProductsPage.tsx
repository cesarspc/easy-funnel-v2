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
import type { MastershopProductMapping, Product, ProductVariantOption } from "../../api";
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

interface EditFormValues {
  name: string;
  price: string;
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

interface MappingFormRow {
  variantSelection: Record<string, string>;
  productId: string;
  variantId: string;
  weight: string;
}

function variantCombinations(options: ProductVariantOption[] = []): Record<string, string>[] {
  if (options.length === 0) return [{}];
  return options.reduce<Record<string, string>[]>(
    (rows, option) =>
      rows.flatMap((row) => option.values.map((value) => ({ ...row, [option.name]: value }))),
    [{}],
  );
}

function mappingLabel(selection: Record<string, string>): string {
  const values = Object.entries(selection).map(([name, value]) => `${name}: ${value}`);
  return values.length ? values.join(" · ") : "Producto sin variantes";
}

function mappingKey(selection: Record<string, string>): string {
  return JSON.stringify(Object.entries(selection).sort(([left], [right]) => left.localeCompare(right)));
}

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
  const [editProduct, setEditProduct] = useState<Product | null>(null);
  const [editForm, setEditForm] = useState<EditFormValues>({ name: "", price: "" });
  const [editFieldErrors, setEditFieldErrors] = useState<Record<string, string>>({});
  const [editError, setEditError] = useState<string | null>(null);
  const [editSaving, setEditSaving] = useState(false);
  const [mappingProduct, setMappingProduct] = useState<Product | null>(null);
  const [mappingRows, setMappingRows] = useState<MappingFormRow[]>([]);
  const [mappingLoading, setMappingLoading] = useState(false);
  const [mappingSaving, setMappingSaving] = useState(false);
  const [mappingError, setMappingError] = useState<string | null>(null);

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
  const handleEditModalClose = useCallback(() => setEditProduct(null), []);

  function openEditModal(product: Product) {
    setEditProduct(product);
    setEditForm({ name: product.name, price: String(product.price) });
    setEditFieldErrors({});
    setEditError(null);
  }

  async function handleEditSubmit(event: FormEvent) {
    event.preventDefault();
    if (!editProduct) return;
    setEditError(null);
    setEditFieldErrors({});

    const price = Number(editForm.price);
    if (!Number.isFinite(price)) {
      setEditFieldErrors({ price: "Ingresa un precio válido." });
      return;
    }

    setEditSaving(true);
    try {
      const updated = await productsApi.update(editProduct.id, {
        name: editForm.name,
        price,
      });
      setProducts((list) => list.map((product) => (
        product.id === updated.id ? updated : product
      )));
      setEditProduct(null);
    } catch (err) {
      if (err instanceof ApiError) {
        setEditError(err.message);
        if (err.fieldErrors) setEditFieldErrors(err.fieldErrors);
      } else {
        setEditError("No se pudo actualizar el producto.");
      }
    } finally {
      setEditSaving(false);
    }
  }

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

  async function openMappings(product: Product) {
    setMappingProduct(product);
    setMappingLoading(true);
    setMappingError(null);
    const combinations = variantCombinations(product.variant_options);
    try {
      const response = await productsApi.getMastershopMappings(product.id);
      setMappingRows(
        combinations.map((selection) => {
          const stored = response.mappings.find(
            (mapping) => mappingKey(mapping.variant_selection) === mappingKey(selection),
          );
          return {
            variantSelection: selection,
            productId: stored ? String(stored.mastershop_product_id) : "",
            variantId: stored?.mastershop_variant_id ? String(stored.mastershop_variant_id) : "",
            weight: stored ? String(stored.weight) : "1",
          };
        }),
      );
    } catch (err) {
      setMappingError(
        err instanceof ApiError ? err.message : "No se pudo cargar la configuración MasterShop.",
      );
    } finally {
      setMappingLoading(false);
    }
  }

  async function saveMappings(event: FormEvent) {
    event.preventDefault();
    if (!mappingProduct) return;
    setMappingSaving(true);
    setMappingError(null);
    const mappings: MastershopProductMapping[] = mappingRows.map((row) => ({
      variant_selection: row.variantSelection,
      mastershop_product_id: Number(row.productId),
      mastershop_variant_id: row.variantId ? Number(row.variantId) : null,
      weight: Number(row.weight),
    }));
    try {
      await productsApi.replaceMastershopMappings(mappingProduct.id, mappings);
      setMappingProduct(null);
    } catch (err) {
      setMappingError(
        err instanceof ApiError ? err.message : "No se pudo guardar la configuración MasterShop.",
      );
    } finally {
      setMappingSaving(false);
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

      <Modal
        isOpen={editProduct !== null}
        onClose={handleEditModalClose}
        title={`Editar producto · ${editProduct?.name ?? ""}`}
        subtitle="La landing usará estos datos de inmediato. Los totales de pedidos existentes no cambian."
      >
        <form className="products-page__create-form" onSubmit={handleEditSubmit} noValidate>
          {editError && (
            <p className="products-page__error" role="alert">
              {editError}
            </p>
          )}
          <FormField
            name="edit-product-name"
            label="Nombre"
            value={editForm.name}
            onChange={(event) => setEditForm((form) => ({ ...form, name: event.target.value }))}
            error={editFieldErrors.name}
            maxLength={160}
            required
            autoComplete="off"
          />
          <FormField
            name="edit-product-price"
            label="Precio (COP)"
            type="number"
            inputMode="decimal"
            min={0.01}
            max={999999999.99}
            step={0.01}
            value={editForm.price}
            onChange={(event) => setEditForm((form) => ({ ...form, price: event.target.value }))}
            error={editFieldErrors.price}
            required
          />
          <div className="products-page__create-form-actions">
            <button
              type="button"
              className="products-table__action"
              onClick={handleEditModalClose}
              disabled={editSaving}
            >
              Cancelar
            </button>
            <button
              type="submit"
              className="products-table__action products-table__action--primary"
              disabled={editSaving}
            >
              {editSaving ? "Guardando…" : "Guardar cambios"}
            </button>
          </div>
        </form>
      </Modal>

      <Modal
        isOpen={mappingProduct !== null}
        onClose={() => setMappingProduct(null)}
        title={`MasterShop · ${mappingProduct?.name ?? ""}`}
        subtitle="Relaciona cada variante local con los identificadores de MasterShop."
      >
        {mappingLoading ? (
          <p>Cargando configuración…</p>
        ) : (
          <form className="products-page__mapping-form" onSubmit={saveMappings} noValidate>
            {mappingError && <p className="products-page__error" role="alert">{mappingError}</p>}
            {mappingRows.map((row, index) => (
              <fieldset className="products-page__mapping-row" key={mappingLabel(row.variantSelection)}>
                <legend>{mappingLabel(row.variantSelection)}</legend>
                <FormField
                  name={`mastershop-product-${index}`}
                  label="ID producto MasterShop"
                  type="number"
                  min={1}
                  required
                  value={row.productId}
                  onChange={(event) => setMappingRows((rows) => rows.map((item, itemIndex) =>
                    itemIndex === index ? { ...item, productId: event.target.value } : item
                  ))}
                />
                {(mappingProduct?.variant_options?.length ?? 0) > 0 && (
                  <FormField
                    name={`mastershop-variant-${index}`}
                    label="ID variante MasterShop"
                    type="number"
                    min={1}
                    required
                    value={row.variantId}
                    onChange={(event) => setMappingRows((rows) => rows.map((item, itemIndex) =>
                      itemIndex === index ? { ...item, variantId: event.target.value } : item
                    ))}
                  />
                )}
                <FormField
                  name={`mastershop-weight-${index}`}
                  label="Peso"
                  type="number"
                  min={0.001}
                  step={0.001}
                  required
                  value={row.weight}
                  onChange={(event) => setMappingRows((rows) => rows.map((item, itemIndex) =>
                    itemIndex === index ? { ...item, weight: event.target.value } : item
                  ))}
                />
              </fieldset>
            ))}
            <div className="products-page__create-form-actions">
              <button type="button" className="products-table__action" onClick={() => setMappingProduct(null)}>
                Cancelar
              </button>
              <button type="submit" className="products-table__action products-table__action--primary" disabled={mappingSaving}>
                {mappingSaving ? "Guardando…" : "Guardar configuración"}
              </button>
            </div>
          </form>
        )}
      </Modal>

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
                        <button
                          type="button"
                          className="products-table__action"
                          onClick={() => openEditModal(product)}
                          aria-label={`Editar producto ${product.name}`}
                        >
                          Editar producto
                        </button>
                        {product.landing_id && (
                          <Link
                            className="products-table__action products-table__action--primary"
                            to={`/admin/landings/${product.landing_id}`}
                          >
                            Editar landing
                          </Link>
                        )}
                        <button
                          type="button"
                          className="products-table__action"
                          onClick={() => void openMappings(product)}
                        >
                          MasterShop
                        </button>
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
