/**
 * Analytics dashboard (Requirements 8.11-8.13, 8.21, 8.19-8.20). One shared
 * inclusive date range drives three queries: orders per day, per-landing
 * performance, and daily fraud rate. Rates arrive pre-computed (0-1) from
 * the backend and are only formatted here, never recomputed client-side.
 *
 * `/admin/analytics/landings` returns every landing (including drafts) with
 * no name attached, so results are joined against `GET /admin/landings` for
 * `product_name`/`slug` display. Trends render as inline SVG — no charting
 * library, per the no-new-dependency constraint.
 */

import { useEffect, useMemo, useState, type FormEvent } from "react";
import type { FraudAnalytics, LandingAnalytics, LandingSummary, OrdersPerDay } from "../../api";
import { analyticsApi, ApiError, landingsApi } from "../../api";
import "./AnalyticsPage.css";

const PERCENT_FORMATTER = new Intl.NumberFormat("es-CO", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

const SHORT_DATE_FORMATTER = new Intl.DateTimeFormat("es-CO", {
  day: "2-digit",
  month: "short",
});

const DEFAULT_RANGE_DAYS = 7;

function isoDaysAgo(days: number): string {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() - days);
  return date.toISOString().slice(0, 10);
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

interface RangeForm {
  dateFrom: string;
  dateTo: string;
}

/** Minimal, dependency-free inline line chart for a `{label, value}` series. */
function TrendChart({
  points,
  formatValue,
  emptyMessage,
}: {
  points: { label: string; value: number }[];
  formatValue: (value: number) => string;
  emptyMessage: string;
}) {
  if (points.length === 0) {
    return <p className="analytics-chart__empty">{emptyMessage}</p>;
  }

  const width = 640;
  const height = 160;
  const paddingX = 12;
  const paddingY = 16;
  const maxValue = Math.max(...points.map((p) => p.value), 1);
  const innerWidth = width - paddingX * 2;
  const innerHeight = height - paddingY * 2;
  const stepX = points.length > 1 ? innerWidth / (points.length - 1) : 0;

  const coords = points.map((point, index) => {
    const x = paddingX + stepX * index;
    const y = paddingY + innerHeight - (point.value / maxValue) * innerHeight;
    return { ...point, x, y };
  });

  const path = coords.map((c, i) => `${i === 0 ? "M" : "L"}${c.x},${c.y}`).join(" ");

  return (
    <div className="analytics-chart">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="analytics-chart__svg"
        role="img"
        aria-label={points.map((p) => `${p.label}: ${formatValue(p.value)}`).join(", ")}
      >
        <line
          x1={paddingX}
          y1={paddingY + innerHeight}
          x2={width - paddingX}
          y2={paddingY + innerHeight}
          className="analytics-chart__axis"
        />
        <path d={path} className="analytics-chart__line" fill="none" />
        {coords.map((c) => (
          <circle key={c.label} cx={c.x} cy={c.y} r={3} className="analytics-chart__point" />
        ))}
      </svg>
      <div className="analytics-chart__legend">
        {coords.map((c) => (
          <span key={c.label} className="analytics-chart__legend-item">
            <strong>{c.label}</strong> {formatValue(c.value)}
          </span>
        ))}
      </div>
    </div>
  );
}

export function AnalyticsPage() {
  const [range, setRange] = useState<RangeForm>({
    dateFrom: isoDaysAgo(DEFAULT_RANGE_DAYS),
    dateTo: todayIso(),
  });
  const [appliedRange, setAppliedRange] = useState<RangeForm>(range);
  const [rangeError, setRangeError] = useState<string | null>(null);
  const [rangeFieldErrors, setRangeFieldErrors] = useState<Record<string, string>>({});

  const [ordersPerDay, setOrdersPerDay] = useState<OrdersPerDay[]>([]);
  const [landingAnalytics, setLandingAnalytics] = useState<LandingAnalytics[]>([]);
  const [landings, setLandings] = useState<LandingSummary[]>([]);
  const [fraudAnalytics, setFraudAnalytics] = useState<FraudAnalytics[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setRangeError(null);
    setRangeFieldErrors({});

    Promise.all([
      analyticsApi.getOrdersPerDay(appliedRange.dateFrom, appliedRange.dateTo),
      analyticsApi.getLandingAnalytics(appliedRange.dateFrom, appliedRange.dateTo),
      analyticsApi.getFraudAnalytics(appliedRange.dateFrom, appliedRange.dateTo),
      landingsApi.list(true),
    ])
      .then(([orders, landingRows, fraud, landingList]) => {
        if (!active) return;
        setOrdersPerDay(orders);
        setLandingAnalytics(landingRows);
        setFraudAnalytics(fraud);
        setLandings(landingList.landings);
      })
      .catch((err) => {
        if (!active) return;
        if (err instanceof ApiError) {
          setRangeError(err.message);
          if (err.fieldErrors) setRangeFieldErrors(err.fieldErrors);
        } else {
          setRangeError("No se pudieron cargar las analíticas.");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [appliedRange]);

  function handleApplyRange(event: FormEvent) {
    event.preventDefault();
    setAppliedRange(range);
  }

  const landingsById = useMemo(
    () => new Map(landings.map((landing) => [landing.id, landing])),
    [landings],
  );

  const ordersChartPoints = useMemo(
    () =>
      [...ordersPerDay]
        .sort((a, b) => a.date.localeCompare(b.date))
        .map((row) => ({
          label: SHORT_DATE_FORMATTER.format(new Date(`${row.date}T00:00:00Z`)),
          value: row.count,
        })),
    [ordersPerDay],
  );

  const fraudChartPoints = useMemo(
    () =>
      [...fraudAnalytics]
        .sort((a, b) => a.date.localeCompare(b.date))
        .map((row) => ({
          label: SHORT_DATE_FORMATTER.format(new Date(`${row.date}T00:00:00Z`)),
          value: row.flagged_fraud_rate,
        })),
    [fraudAnalytics],
  );

  const ordersNewestFirst = useMemo(
    () => [...ordersPerDay].sort((a, b) => b.date.localeCompare(a.date)),
    [ordersPerDay],
  );

  const fraudNewestFirst = useMemo(
    () => [...fraudAnalytics].sort((a, b) => b.date.localeCompare(a.date)),
    [fraudAnalytics],
  );

  return (
    <div className="analytics-page">
      <div className="analytics-page__header">
        <h1 className="analytics-page__title">Analítica</h1>
      </div>

      <form className="analytics-range" onSubmit={handleApplyRange} aria-label="Rango de fechas">
        <div className="analytics-range__field">
          <label className="analytics-range__label" htmlFor="analytics-date-from">
            Desde
          </label>
          <input
            id="analytics-date-from"
            className="analytics-range__input"
            type="date"
            value={range.dateFrom}
            max={range.dateTo}
            aria-describedby={rangeFieldErrors.date_from ? "analytics-date-from-error" : undefined}
            aria-invalid={rangeFieldErrors.date_from ? true : undefined}
            onChange={(event) => setRange((r) => ({ ...r, dateFrom: event.target.value }))}
          />
          {rangeFieldErrors.date_from && (
            <p className="analytics-range__error" id="analytics-date-from-error" role="alert">
              {rangeFieldErrors.date_from}
            </p>
          )}
        </div>

        <div className="analytics-range__field">
          <label className="analytics-range__label" htmlFor="analytics-date-to">
            Hasta
          </label>
          <input
            id="analytics-date-to"
            className="analytics-range__input"
            type="date"
            value={range.dateTo}
            min={range.dateFrom}
            aria-describedby={rangeFieldErrors.date_to ? "analytics-date-to-error" : undefined}
            aria-invalid={rangeFieldErrors.date_to ? true : undefined}
            onChange={(event) => setRange((r) => ({ ...r, dateTo: event.target.value }))}
          />
          {rangeFieldErrors.date_to && (
            <p className="analytics-range__error" id="analytics-date-to-error" role="alert">
              {rangeFieldErrors.date_to}
            </p>
          )}
        </div>

        <button type="submit" className="analytics-table__action analytics-table__action--primary">
          Aplicar
        </button>
      </form>

      {rangeError && (
        <p className="analytics-page__error" role="alert">
          {rangeError}
        </p>
      )}

      <section className="analytics-panel" aria-labelledby="orders-per-day-heading">
        <h2 className="analytics-panel__title" id="orders-per-day-heading">
          Pedidos por día
        </h2>
        {loading ? (
          <p className="analytics-page__muted">Cargando…</p>
        ) : (
          <>
            <TrendChart
              points={ordersChartPoints}
              formatValue={(value) => String(value)}
              emptyMessage="No hay pedidos en el rango seleccionado."
            />
            <div className="analytics-table-wrap">
              <table className="analytics-table">
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Pedidos</th>
                  </tr>
                </thead>
                <tbody>
                  {ordersNewestFirst.length === 0 ? (
                    <tr>
                      <td colSpan={2} className="analytics-table__empty">
                        No hay pedidos en el rango seleccionado.
                      </td>
                    </tr>
                  ) : (
                    ordersNewestFirst.map((row) => (
                      <tr key={row.date}>
                        <td className="analytics-table__data">{row.date}</td>
                        <td className="analytics-table__data">{row.count}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>

      <section className="analytics-panel" aria-labelledby="landings-heading">
        <h2 className="analytics-panel__title" id="landings-heading">
          Rendimiento por landing
        </h2>
        {loading ? (
          <p className="analytics-page__muted">Cargando…</p>
        ) : (
          <div className="analytics-table-wrap">
            <table className="analytics-table">
              <thead>
                <tr>
                  <th>Producto</th>
                  <th>Slug</th>
                  <th>Vistas</th>
                  <th>Clics CTA</th>
                  <th>Pedidos</th>
                  <th>Conversión</th>
                </tr>
              </thead>
              <tbody>
                {landingAnalytics.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="analytics-table__empty">
                      No hay datos de landings en el rango seleccionado.
                    </td>
                  </tr>
                ) : (
                  landingAnalytics.map((row) => {
                    const landing = landingsById.get(row.landing_id);
                    return (
                      <tr key={row.landing_id}>
                        <td>{landing?.product_name ?? `Landing #${row.landing_id}`}</td>
                        <td className="analytics-table__data">
                          {landing ? `/p/${landing.slug}` : "—"}
                        </td>
                        <td className="analytics-table__data">{row.views}</td>
                        <td className="analytics-table__data">{row.clicks}</td>
                        <td className="analytics-table__data">{row.orders}</td>
                        <td className="analytics-table__data">
                          {PERCENT_FORMATTER.format(row.conversion_rate)}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="analytics-panel" aria-labelledby="fraud-rate-heading">
        <h2 className="analytics-panel__title" id="fraud-rate-heading">
          Tasa de fraude por día
        </h2>
        {loading ? (
          <p className="analytics-page__muted">Cargando…</p>
        ) : (
          <>
            <TrendChart
              points={fraudChartPoints}
              formatValue={(value) => PERCENT_FORMATTER.format(value)}
              emptyMessage="No hay pedidos en el rango seleccionado."
            />
            <div className="analytics-table-wrap">
              <table className="analytics-table">
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Marcados</th>
                    <th>Total</th>
                    <th>Tasa de fraude</th>
                  </tr>
                </thead>
                <tbody>
                  {fraudNewestFirst.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="analytics-table__empty">
                        No hay pedidos en el rango seleccionado.
                      </td>
                    </tr>
                  ) : (
                    fraudNewestFirst.map((row) => (
                      <tr key={row.date}>
                        <td className="analytics-table__data">{row.date}</td>
                        <td className="analytics-table__data">{row.flagged_orders}</td>
                        <td className="analytics-table__data">{row.total_orders}</td>
                        <td className="analytics-table__data">
                          {PERCENT_FORMATTER.format(row.flagged_fraud_rate)}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
