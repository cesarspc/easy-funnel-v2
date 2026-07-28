/**
 * Landing list (Requirement 8.3). One row per product landing with its
 * publication status, slug, and banner count; "Gestionar" opens the editor
 * where banners, CTA placement, and publication are managed.
 */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { StatusPill } from "../../components";
import type { LandingSummary } from "../../api";
import { ApiError, landingsApi } from "../../api";
import "./LandingsPage.css";

export function LandingsPage() {
  const [landings, setLandings] = useState<LandingSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    landingsApi
      .list()
      .then((response) => {
        if (active) setLandings(response.landings);
      })
      .catch((err) => {
        if (active) {
          setError(err instanceof ApiError ? err.message : "No se pudieron cargar las landings.");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="landings-page">
      <div className="landings-page__header">
        <h1 className="landings-page__title">Landings</h1>
      </div>

      {error && (
        <p className="landings-page__error" role="alert">
          {error}
        </p>
      )}

      <div className="landings-page__table-wrap">
        <table className="landings-table">
          <thead>
            <tr>
              <th>Producto</th>
              <th>Slug</th>
              <th>Banners</th>
              <th>Estado</th>
              <th>
                <span className="sr-only">Acciones</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} className="landings-table__empty">
                  Cargando landings…
                </td>
              </tr>
            ) : landings.length === 0 ? (
              <tr>
                <td colSpan={5} className="landings-table__empty">
                  Todavía no hay landings. Crea un producto y su landing se creará contigo.
                </td>
              </tr>
            ) : (
              landings.map((landing) => (
                <tr key={landing.id}>
                  <td>{landing.product_name}</td>
                  <td className="landings-table__data">/p/{landing.slug}</td>
                  <td className="landings-table__data">{landing.banner_count}</td>
                  <td>
                    <StatusPill status={landing.status} />
                  </td>
                  <td className="landings-table__actions">
                    <span className="landings-table__actions-row">
                      <Link className="landings-table__action" to={`/admin/landings/${landing.id}`}>
                        Gestionar
                      </Link>
                      {landing.status === "published" && landing.product_status === "active" ? (
                        <a
                          href={`/p/${landing.slug}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="landings-table__action"
                        >
                          Ver pública
                        </a>
                      ) : (
                        <button
                          type="button"
                          className="landings-table__action"
                          disabled
                          title="La landing pública solo responde cuando el producto está activo y la landing publicada."
                        >
                          Ver pública
                        </button>
                      )}
                    </span>
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
