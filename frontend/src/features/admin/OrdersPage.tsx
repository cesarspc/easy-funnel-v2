/**
 * Orders list (Requirement 8.4-8.9, 8.16-8.18). Filters by status,
 * product, landing, and inclusive creation-date range; combines filters
 * with AND semantics via ordersApi.list. CSV export reuses active filters.
 */

import { useEffect, useMemo, useState } from "react";
import { StatusPill } from "../../components";
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

export function OrdersPage() {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

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
              <th>Estado</th>
              <th>Creado</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="orders-table__empty">
                  Cargando pedidos…
                </td>
              </tr>
            ) : orders.length === 0 ? (
              <tr>
                <td colSpan={7} className="orders-table__empty">
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
                  <td>
                    <StatusPill status={order.status} />
                  </td>
                  <td className="orders-table__data">
                    {DATE_FORMATTER.format(new Date(order.created_at))}
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
