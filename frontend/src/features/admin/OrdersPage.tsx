/**
 * Orders list (Requirement 8.4-8.9, 8.16-8.18). Filters by status,
 * product, landing, and inclusive creation-date range; combines filters
 * with AND semantics via ordersApi.list. CSV export reuses active filters.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { StatusPill } from "../../components";
import { Modal } from "../../components/Modal";
import type { Order } from "../../api";
import { ApiError, ordersApi } from "../../api";
import "./OrdersPage.css";

const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "Todos los estados" },
  { value: "pending", label: "Pendiente" },
  { value: "confirmed", label: "Confirmado" },
  { value: "shipped", label: "Enviado" },
  { value: "delivered", label: "Entregado" },
  { value: "cancelled", label: "Cancelado" },
  { value: "flagged_fraud", label: "Marcado para revisión" },
];

const DATE_FORMATTER = new Intl.DateTimeFormat("es-CO", {
  day: "2-digit",
  month: "short",
  year: "numeric",
});

const DATE_TIME_FORMATTER = new Intl.DateTimeFormat("es-CO", {
  dateStyle: "medium",
  timeStyle: "short",
});

const CURRENCY = new Intl.NumberFormat("es-CO", {
  style: "currency",
  currency: "COP",
  maximumFractionDigits: 0,
});

interface Filters {
  status: string;
  productId: string;
  landingId: string;
  dateFrom: string;
  dateTo: string;
}

const EMPTY_FILTERS: Filters = {
  status: "",
  productId: "",
  landingId: "",
  dateFrom: "",
  dateTo: "",
};

function buildParams(filters: Filters) {
  return {
    status: filters.status || undefined,
    product_id: filters.productId ? Number(filters.productId) : undefined,
    landing_id: filters.landingId ? Number(filters.landingId) : undefined,
    date_from: filters.dateFrom || undefined,
    date_to: filters.dateTo || undefined,
  };
}

function variantSummary(order: Order): string {
  return (order.variant_selections ?? [])
    .map(
      (selection, index) =>
        `${index + 1}: ${Object.entries(selection)
          .map(([name, value]) => `${name} ${value}`)
          .join(", ")}`,
    )
    .join(" · ");
}

export function OrdersPage() {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [detailOrderId, setDetailOrderId] = useState<number | null>(null);
  const [detailOrder, setDetailOrder] = useState<Order | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const params = useMemo(() => buildParams(filters), [filters]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    ordersApi
      .list(params)
      .then((response) => {
        if (cancelled) return;
        setOrders(response.orders);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "No se pudieron cargar los pedidos.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [params]);

  async function handleExport() {
    setExporting(true);
    try {
      const blob = await ordersApi.export(params);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "pedidos.csv";
      link.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }

  async function openOrderDetails(orderId: number) {
    setDetailOrderId(orderId);
    setDetailOrder(null);
    setDetailError(null);
    setDetailLoading(true);
    try {
      setDetailOrder(await ordersApi.get(orderId));
    } catch (err) {
      setDetailError(
        err instanceof ApiError ? err.message : "No se pudieron cargar los detalles del pedido.",
      );
    } finally {
      setDetailLoading(false);
    }
  }

  const closeOrderDetails = useCallback(() => {
    setDetailOrderId(null);
    setDetailOrder(null);
    setDetailError(null);
  }, []);

  return (
    <div className="orders-page">
      <div className="orders-page__header">
        <h1 className="orders-page__title">Pedidos</h1>
        <button
          type="button"
          className="orders-page__export"
          onClick={() => void handleExport()}
          disabled={exporting || loading}
        >
          {exporting ? "Exportando…" : "Exportar CSV"}
        </button>
      </div>

      <form className="orders-page__filters" aria-label="Filtros de pedidos">
        <div className="orders-page__field">
          <label htmlFor="filter-status">Estado</label>
          <select
            id="filter-status"
            value={filters.status}
            onChange={(event) => setFilters((f) => ({ ...f, status: event.target.value }))}
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className="orders-page__field">
          <label htmlFor="filter-product">ID de producto</label>
          <input
            id="filter-product"
            type="number"
            min="1"
            inputMode="numeric"
            value={filters.productId}
            onChange={(event) => setFilters((f) => ({ ...f, productId: event.target.value }))}
          />
        </div>

        <div className="orders-page__field">
          <label htmlFor="filter-landing">ID de landing</label>
          <input
            id="filter-landing"
            type="number"
            min="1"
            inputMode="numeric"
            value={filters.landingId}
            onChange={(event) => setFilters((f) => ({ ...f, landingId: event.target.value }))}
          />
        </div>

        <div className="orders-page__field">
          <label htmlFor="filter-from">Desde</label>
          <input
            id="filter-from"
            type="date"
            value={filters.dateFrom}
            onChange={(event) => setFilters((f) => ({ ...f, dateFrom: event.target.value }))}
          />
        </div>

        <div className="orders-page__field">
          <label htmlFor="filter-to">Hasta</label>
          <input
            id="filter-to"
            type="date"
            value={filters.dateTo}
            onChange={(event) => setFilters((f) => ({ ...f, dateTo: event.target.value }))}
          />
        </div>

        {(filters.status || filters.productId || filters.landingId || filters.dateFrom || filters.dateTo) && (
          <button
            type="button"
            className="orders-page__clear"
            onClick={() => setFilters(EMPTY_FILTERS)}
          >
            Limpiar filtros
          </button>
        )}
      </form>

      {error && (
        <p className="orders-page__error" role="alert">
          {error}
        </p>
      )}

      <div className="orders-page__table-wrap">
        <table className="orders-table">
          <thead>
            <tr>
              <th>Pedido</th>
              <th>Cliente</th>
              <th>Teléfono</th>
              <th>Ciudad</th>
              <th>Cant.</th>
              <th>Variantes</th>
              <th>Estado</th>
              <th>Creado</th>
              <th><span className="sr-only">Acciones</span></th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={9} className="orders-table__empty">
                  Cargando pedidos…
                </td>
              </tr>
            ) : orders.length === 0 ? (
              <tr>
                <td colSpan={9} className="orders-table__empty">
                  No hay pedidos que coincidan con los filtros actuales.
                </td>
              </tr>
            ) : (
              orders.map((order) => (
                <tr key={order.id}>
                  <td className="orders-table__data">#{order.id}</td>
                  <td>{order.customer_name}</td>
                  <td className="orders-table__data">{order.phone_e164}</td>
                  <td>{order.city}</td>
                  <td className="orders-table__data">{order.quantity}</td>
                  <td>{variantSummary(order) || "—"}</td>
                  <td>
                    <StatusPill status={order.status} />
                  </td>
                  <td className="orders-table__data">
                    {DATE_FORMATTER.format(new Date(order.created_at))}
                  </td>
                  <td>
                    <button
                      type="button"
                      className="orders-table__view"
                      aria-label={`Ver todos los detalles del pedido #${order.id}`}
                      title="Ver detalles"
                      onClick={() => void openOrderDetails(order.id)}
                    >
                      <svg viewBox="0 0 24 24" aria-hidden="true">
                        <path d="M12 5C6.5 5 2.1 9.1.3 12c1.8 2.9 6.2 7 11.7 7s9.9-4.1 11.7-7C21.9 9.1 17.5 5 12 5Zm0 11a4 4 0 1 1 0-8 4 4 0 0 1 0 8Zm0-2a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z" />
                      </svg>
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <Modal
        isOpen={detailOrderId !== null}
        onClose={closeOrderDetails}
        title={`Pedido #${detailOrderId ?? ""}`}
        subtitle="Información completa registrada al crear el pedido"
      >
        {detailLoading && <p className="order-detail__state">Cargando detalles…</p>}
        {detailError && <p className="orders-page__error" role="alert">{detailError}</p>}
        {detailOrder && (
          <div className="order-detail">
            <section className="order-detail__section">
              <h3>Pedido y cobro</h3>
              <dl className="order-detail__grid">
                <div><dt>Estado</dt><dd><StatusPill status={detailOrder.status} /></dd></div>
                <div><dt>Cantidad</dt><dd>{detailOrder.quantity}</dd></div>
                <div><dt>Precio unitario</dt><dd>{CURRENCY.format(detailOrder.unit_price)}</dd></div>
                <div><dt>Descuento</dt><dd>{detailOrder.discount_percent}%</dd></div>
                <div><dt>Ahorro exacto</dt><dd>{CURRENCY.format((detailOrder.unit_price * detailOrder.quantity) - detailOrder.total_price)}</dd></div>
                <div className="order-detail__wide"><dt>Total a cobrar</dt><dd className="order-detail__total">{CURRENCY.format(detailOrder.total_price)}</dd></div>
                <div><dt>Producto</dt><dd>{detailOrder.product_name ?? `ID ${detailOrder.product_id}`}</dd></div>
                <div><dt>SKU</dt><dd>{detailOrder.product_sku ?? "—"}</dd></div>
                <div><dt>ID producto</dt><dd>{detailOrder.product_id}</dd></div>
                <div><dt>ID landing</dt><dd>{detailOrder.landing_id}</dd></div>
                <div className="order-detail__wide"><dt>Slug de landing</dt><dd>{detailOrder.landing_slug}</dd></div>
              </dl>
            </section>

            <section className="order-detail__section">
              <h3>Cliente y entrega</h3>
              <dl className="order-detail__grid">
                <div><dt>Nombre</dt><dd>{detailOrder.customer_name}</dd></div>
                <div><dt>Teléfono</dt><dd>{detailOrder.phone_e164}</dd></div>
                <div><dt>Departamento</dt><dd>{detailOrder.department}</dd></div>
                <div><dt>Ciudad</dt><dd>{detailOrder.city}</dd></div>
                <div className="order-detail__wide"><dt>Dirección</dt><dd>{detailOrder.address}</dd></div>
              </dl>
            </section>

            <section className="order-detail__section">
              <h3>Variantes por unidad</h3>
              {(detailOrder.variant_selections ?? []).length > 0 ? (
                <ol className="order-detail__variants">
                  {(detailOrder.variant_selections ?? []).map((selection, index) => (
                    <li key={index}>
                      <strong>Unidad {index + 1}</strong>
                      <span>{Object.entries(selection).map(([name, value]) => `${name}: ${value}`).join(" · ")}</span>
                    </li>
                  ))}
                </ol>
              ) : <p className="order-detail__empty">Este producto no usa variantes.</p>}
            </section>

            <section className="order-detail__section">
              <h3>Fraude</h3>
              {(detailOrder.fraud_flags ?? []).length > 0 ? (
                <ul className="order-detail__flags">
                  {(detailOrder.fraud_flags ?? []).map((flag, index) => (
                    <li key={flag.id ?? index}>
                      <strong>{flag.flag_type}</strong>
                      {flag.created_at && (
                        <small>{DATE_TIME_FORMATTER.format(new Date(flag.created_at))}</small>
                      )}
                      <pre>{JSON.stringify(flag.detail, null, 2)}</pre>
                    </li>
                  ))}
                </ul>
              ) : <p className="order-detail__empty">Sin alertas de fraude.</p>}
            </section>

            <section className="order-detail__section">
              <h3>Registro técnico</h3>
              <dl className="order-detail__grid">
                <div><dt>IP</dt><dd>{detailOrder.ip_address}</dd></div>
                <div><dt>Clave telefónica normalizada</dt><dd>{detailOrder.phone_normalized_key ?? "—"}</dd></div>
                <div><dt>Creado</dt><dd>{DATE_TIME_FORMATTER.format(new Date(detailOrder.created_at))}</dd></div>
                <div><dt>Actualizado</dt><dd>{DATE_TIME_FORMATTER.format(new Date(detailOrder.updated_at))}</dd></div>
                <div className="order-detail__wide"><dt>User agent</dt><dd className="order-detail__break">{detailOrder.user_agent}</dd></div>
              </dl>
            </section>
          </div>
        )}
      </Modal>
    </div>
  );
}
