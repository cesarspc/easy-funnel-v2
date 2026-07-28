/**
 * Products list (Requirement 8.1-8.2). Activate/pause toggle availability
 * without deleting data; retire applies Soft_Deletion and is confirmed
 * explicitly, naming it as retirement with historical data preserved
 * (Requirement 2.13, 8.2).
 */

import { useEffect, useState } from "react";
import { StatusPill } from "../../components";
import type { Product } from "../../api";
import { ApiError, productsApi } from "../../api";
import "./ProductsPage.css";

const CURRENCY_FORMATTER = new Intl.NumberFormat("es-CO", {
  style: "currency",
  currency: "COP",
  maximumFractionDigits: 0,
});

export function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [confirmRetireId, setConfirmRetireId] = useState<number | null>(null);

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
      </div>

      {error && (
        <p className="products-page__error" role="alert">
          {error}
        </p>
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
