/**
 * Fraud configuration screen (Requirements 6.20-6.24, 8.10, 8.19-8.20).
 * Three independent panels — Fraud_Configuration, Manual_Blacklist, and
 * GeoIP_Rules — each with its own busy/error/notice state so a rejected
 * mutation in one panel never blocks the others. Every field-specific
 * backend error (`{field, message}`) is bound to the control that produced
 * it through `aria-describedby`/`aria-invalid` and announced with
 * `role="alert"`, following LandingEditorPage's pattern.
 *
 * Fraud flags themselves live on Orders, not here: the panel links out to
 * the Orders list filtered to `flagged_fraud` rather than re-rendering a
 * second order table.
 */

import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import type { BlacklistEntry, FraudConfig, GeoIpRule } from "../../api";
import { ApiError, fraudApi } from "../../api";
import "./FraudPage.css";

const DATE_FORMATTER = new Intl.DateTimeFormat("es-CO", {
  day: "2-digit",
  month: "short",
  year: "numeric",
});

interface ConfigForm {
  duplicateWindowHours: string;
  duplicateMatchFields: Set<string>;
  rateLimitMax: string;
  rateLimitWindowMinutes: string;
  bannedCities: string;
}

function toConfigForm(config: FraudConfig): ConfigForm {
  return {
    duplicateWindowHours: String(config.duplicate_window_hours),
    duplicateMatchFields: new Set(config.duplicate_match_fields),
    rateLimitMax: String(config.rate_limit_max),
    rateLimitWindowMinutes: String(config.rate_limit_window_minutes),
    bannedCities: (config.banned_cities ?? []).join("\n"),
  };
}

export function FraudPage() {
  // --- Fraud configuration ------------------------------------------------
  const [config, setConfig] = useState<ConfigForm | null>(null);
  const [configLoading, setConfigLoading] = useState(true);
  const [configBusy, setConfigBusy] = useState(false);
  const [configError, setConfigError] = useState<string | null>(null);
  const [configNotice, setConfigNotice] = useState<string | null>(null);
  const [configFieldErrors, setConfigFieldErrors] = useState<Record<string, string>>({});

  // --- Manual blacklist -----------------------------------------------------
  const [blacklist, setBlacklist] = useState<BlacklistEntry[]>([]);
  const [blacklistLoading, setBlacklistLoading] = useState(true);
  const [blacklistBusy, setBlacklistBusy] = useState(false);
  const [blacklistError, setBlacklistError] = useState<string | null>(null);
  const [blacklistNotice, setBlacklistNotice] = useState<string | null>(null);
  const [blacklistFieldErrors, setBlacklistFieldErrors] = useState<Record<string, string>>({});
  const [newEntryType, setNewEntryType] = useState<"phone" | "ip">("phone");
  const [newEntryValue, setNewEntryValue] = useState("");
  const [newEntryReason, setNewEntryReason] = useState("");
  const [confirmDeleteBlacklistId, setConfirmDeleteBlacklistId] = useState<number | null>(null);

  // --- GeoIP rules ------------------------------------------------------------
  const [geoipRules, setGeoipRules] = useState<GeoIpRule[]>([]);
  const [geoipLoading, setGeoipLoading] = useState(true);
  const [geoipBusy, setGeoipBusy] = useState(false);
  const [geoipError, setGeoipError] = useState<string | null>(null);
  const [geoipNotice, setGeoipNotice] = useState<string | null>(null);
  const [geoipFieldErrors, setGeoipFieldErrors] = useState<Record<string, string>>({});
  const [newLocationCode, setNewLocationCode] = useState("");
  const [newAction, setNewAction] = useState<"flag" | "block">("flag");
  const [confirmDeleteGeoipId, setConfirmDeleteGeoipId] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    fraudApi
      .getConfig()
      .then((data) => {
        if (active) setConfig(toConfigForm(data));
      })
      .catch((err) => {
        if (active) {
          setConfigError(
            err instanceof ApiError ? err.message : "No se pudo cargar la configuración.",
          );
        }
      })
      .finally(() => {
        if (active) setConfigLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    fraudApi
      .listBlacklist()
      .then((response) => {
        if (active) setBlacklist(response.entries);
      })
      .catch((err) => {
        if (active) {
          setBlacklistError(
            err instanceof ApiError ? err.message : "No se pudo cargar la lista negra.",
          );
        }
      })
      .finally(() => {
        if (active) setBlacklistLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    fraudApi
      .listGeoIpRules()
      .then((response) => {
        if (active) setGeoipRules(response.rules);
      })
      .catch((err) => {
        if (active) {
          setGeoipError(
            err instanceof ApiError ? err.message : "No se pudieron cargar las reglas GeoIP.",
          );
        }
      })
      .finally(() => {
        if (active) setGeoipLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  function toggleMatchField(field: string) {
    setConfig((current) => {
      if (!current) return current;
      const next = new Set(current.duplicateMatchFields);
      if (next.has(field)) next.delete(field);
      else next.add(field);
      return { ...current, duplicateMatchFields: next };
    });
  }

  async function handleSaveConfig(event: FormEvent) {
    event.preventDefault();
    if (!config) return;
    setConfigError(null);
    setConfigNotice(null);
    setConfigFieldErrors({});
    setConfigBusy(true);
    try {
      const updated = await fraudApi.updateConfig({
        duplicate_window_hours: Number(config.duplicateWindowHours),
        duplicate_match_fields: Array.from(config.duplicateMatchFields),
        rate_limit_max: Number(config.rateLimitMax),
        rate_limit_window_minutes: Number(config.rateLimitWindowMinutes),
        banned_cities: config.bannedCities.split(/\r?\n/).map((city) => city.trim()).filter(Boolean),
      });
      setConfig(toConfigForm(updated));
      setConfigNotice("Configuración guardada.");
    } catch (err) {
      if (err instanceof ApiError) {
        setConfigError(err.message);
        if (err.fieldErrors) setConfigFieldErrors(err.fieldErrors);
      } else {
        setConfigError("No se pudo guardar la configuración.");
      }
    } finally {
      setConfigBusy(false);
    }
  }

  async function handleAddBlacklistEntry(event: FormEvent) {
    event.preventDefault();
    setBlacklistError(null);
    setBlacklistNotice(null);
    setBlacklistFieldErrors({});
    setBlacklistBusy(true);
    try {
      const entry = await fraudApi.addBlacklistEntry({
        entry_type: newEntryType,
        value_normalized: newEntryValue,
        reason: newEntryReason,
      });
      setBlacklist((list) => [entry, ...list]);
      setNewEntryValue("");
      setNewEntryReason("");
      setBlacklistNotice("Entrada agregada a la lista negra.");
    } catch (err) {
      if (err instanceof ApiError) {
        setBlacklistError(err.message);
        if (err.fieldErrors) setBlacklistFieldErrors(err.fieldErrors);
      } else {
        setBlacklistError("No se pudo agregar la entrada.");
      }
    } finally {
      setBlacklistBusy(false);
    }
  }

  async function handleRemoveBlacklistEntry(id: number) {
    setBlacklistError(null);
    setBlacklistNotice(null);
    setBlacklistBusy(true);
    try {
      await fraudApi.removeBlacklistEntry(id);
      setBlacklist((list) => list.filter((entry) => entry.id !== id));
      setBlacklistNotice(
        "Entrada eliminada de la lista negra. Las marcas de fraude ya registradas en pedidos históricos se conservan.",
      );
    } catch (err) {
      setBlacklistError(err instanceof ApiError ? err.message : "No se pudo eliminar la entrada.");
    } finally {
      setBlacklistBusy(false);
      setConfirmDeleteBlacklistId(null);
    }
  }

  async function handleAddGeoIpRule(event: FormEvent) {
    event.preventDefault();
    setGeoipError(null);
    setGeoipNotice(null);
    setGeoipFieldErrors({});
    setGeoipBusy(true);
    try {
      const rule = await fraudApi.createGeoIpRule({
        location_code: newLocationCode,
        action: newAction,
      });
      setGeoipRules((rules) => [rule, ...rules]);
      setNewLocationCode("");
      setGeoipNotice("Regla GeoIP creada.");
    } catch (err) {
      if (err instanceof ApiError) {
        setGeoipError(err.message);
        if (err.fieldErrors) setGeoipFieldErrors(err.fieldErrors);
      } else {
        setGeoipError("No se pudo crear la regla.");
      }
    } finally {
      setGeoipBusy(false);
    }
  }

  async function handleToggleGeoIpRule(rule: GeoIpRule) {
    setGeoipError(null);
    setGeoipNotice(null);
    setGeoipBusy(true);
    try {
      const updated = await fraudApi.updateGeoIpRule(rule.id, { enabled: !rule.enabled });
      setGeoipRules((rules) => rules.map((r) => (r.id === rule.id ? updated : r)));
    } catch (err) {
      setGeoipError(err instanceof ApiError ? err.message : "No se pudo actualizar la regla.");
    } finally {
      setGeoipBusy(false);
    }
  }

  async function handleDeleteGeoIpRule(id: number) {
    setGeoipError(null);
    setGeoipNotice(null);
    setGeoipBusy(true);
    try {
      await fraudApi.deleteGeoIpRule(id);
      setGeoipRules((rules) => rules.filter((rule) => rule.id !== id));
      setGeoipNotice(
        "Regla GeoIP eliminada. Las marcas de fraude ya registradas en pedidos históricos se conservan.",
      );
    } catch (err) {
      setGeoipError(err instanceof ApiError ? err.message : "No se pudo eliminar la regla.");
    } finally {
      setGeoipBusy(false);
      setConfirmDeleteGeoipId(null);
    }
  }

  return (
    <div className="fraud-page">
      <div className="fraud-page__header">
        <h1 className="fraud-page__title">Fraude</h1>
        <Link className="fraud-table__action" to="/admin/orders">
          Ver pedidos marcados para revisión
        </Link>
      </div>
      <p className="fraud-page__intro">
        Tanto <code>flag</code> como <code>block</code> generan un pedido marcado
        (<code>flagged_fraud</code>) disponible para revisión en Pedidos — ninguna acción
        descarta una solicitud.
      </p>

      <section className="fraud-panel" aria-labelledby="config-heading">
        <h2 className="fraud-panel__title" id="config-heading">
          Configuración de fraude
        </h2>

        {configError && (
          <p className="fraud-page__error" role="alert">
            {configError}
          </p>
        )}
        {configNotice && (
          <p className="fraud-page__notice" role="status">
            {configNotice}
          </p>
        )}

        {configLoading ? (
          <p className="fraud-page__muted">Cargando configuración…</p>
        ) : config ? (
          <form className="fraud-form" onSubmit={handleSaveConfig}>
            <div className="fraud-field">
              <label className="fraud-field__label" htmlFor="duplicate-window-hours">
                Ventana de duplicados (horas)
              </label>
              <input
                id="duplicate-window-hours"
                className="fraud-field__input"
                type="number"
                min={1}
                step={1}
                value={config.duplicateWindowHours}
                aria-describedby={
                  configFieldErrors.duplicate_window_hours
                    ? "duplicate-window-hours-error"
                    : undefined
                }
                aria-invalid={configFieldErrors.duplicate_window_hours ? true : undefined}
                onChange={(event) =>
                  setConfig((current) =>
                    current
                      ? { ...current, duplicateWindowHours: event.target.value }
                      : current,
                  )
                }
              />
              {configFieldErrors.duplicate_window_hours && (
                <p
                  className="fraud-field__error"
                  id="duplicate-window-hours-error"
                  role="alert"
                >
                  {configFieldErrors.duplicate_window_hours}
                </p>
              )}
            </div>

            <div className="fraud-field">
              <label className="fraud-field__label" htmlFor="banned-cities">
                Ciudades sin cobertura
              </label>
              <textarea
                id="banned-cities"
                className="fraud-field__input fraud-field__textarea"
                value={config.bannedCities}
                rows={7}
                placeholder={"SOACHA\nCALI"}
                aria-describedby={
                  configFieldErrors.banned_cities
                    ? "banned-cities-hint banned-cities-error"
                    : "banned-cities-hint"
                }
                aria-invalid={configFieldErrors.banned_cities ? true : undefined}
                onChange={(event) =>
                  setConfig((current) =>
                    current ? { ...current, bannedCities: event.target.value } : current,
                  )
                }
              />
              <p className="fraud-page__muted" id="banned-cities-hint">
                Una ciudad por línea. Se ocultará del formulario de pedido.
              </p>
              {configFieldErrors.banned_cities && (
                <p className="fraud-field__error" id="banned-cities-error" role="alert">
                  {configFieldErrors.banned_cities}
                </p>
              )}
            </div>

            <fieldset className="fraud-field">
              <legend className="fraud-field__label">Campos que se comparan para duplicados</legend>
              <div className="fraud-checkbox-group">
                <label className="fraud-checkbox">
                  <input
                    type="checkbox"
                    checked={config.duplicateMatchFields.has("phone")}
                    onChange={() => toggleMatchField("phone")}
                  />
                  Teléfono
                </label>
                <label className="fraud-checkbox">
                  <input
                    type="checkbox"
                    checked={config.duplicateMatchFields.has("ip")}
                    onChange={() => toggleMatchField("ip")}
                  />
                  Dirección IP
                </label>
              </div>
              {configFieldErrors.duplicate_match_fields && (
                <p className="fraud-field__error" role="alert">
                  {configFieldErrors.duplicate_match_fields}
                </p>
              )}
            </fieldset>

            <div className="fraud-field">
              <label className="fraud-field__label" htmlFor="rate-limit-max">
                Máximo de intentos
              </label>
              <input
                id="rate-limit-max"
                className="fraud-field__input"
                type="number"
                min={1}
                step={1}
                value={config.rateLimitMax}
                aria-describedby={
                  configFieldErrors.rate_limit_max ? "rate-limit-max-error" : undefined
                }
                aria-invalid={configFieldErrors.rate_limit_max ? true : undefined}
                onChange={(event) =>
                  setConfig((current) =>
                    current ? { ...current, rateLimitMax: event.target.value } : current,
                  )
                }
              />
              {configFieldErrors.rate_limit_max && (
                <p className="fraud-field__error" id="rate-limit-max-error" role="alert">
                  {configFieldErrors.rate_limit_max}
                </p>
              )}
            </div>

            <div className="fraud-field">
              <label className="fraud-field__label" htmlFor="rate-limit-window-minutes">
                Ventana de intentos (minutos)
              </label>
              <input
                id="rate-limit-window-minutes"
                className="fraud-field__input"
                type="number"
                min={1}
                step={1}
                value={config.rateLimitWindowMinutes}
                aria-describedby={
                  configFieldErrors.rate_limit_window_minutes
                    ? "rate-limit-window-minutes-error"
                    : undefined
                }
                aria-invalid={configFieldErrors.rate_limit_window_minutes ? true : undefined}
                onChange={(event) =>
                  setConfig((current) =>
                    current
                      ? { ...current, rateLimitWindowMinutes: event.target.value }
                      : current,
                  )
                }
              />
              {configFieldErrors.rate_limit_window_minutes && (
                <p
                  className="fraud-field__error"
                  id="rate-limit-window-minutes-error"
                  role="alert"
                >
                  {configFieldErrors.rate_limit_window_minutes}
                </p>
              )}
            </div>

            <button
              type="submit"
              className="fraud-table__action fraud-table__action--primary"
              disabled={configBusy}
            >
              Guardar configuración
            </button>
          </form>
        ) : (
          <p className="fraud-page__muted">No se pudo cargar la configuración.</p>
        )}
      </section>

      <section className="fraud-panel" aria-labelledby="blacklist-heading">
        <h2 className="fraud-panel__title" id="blacklist-heading">
          Lista negra manual
        </h2>

        {blacklistError && (
          <p className="fraud-page__error" role="alert">
            {blacklistError}
          </p>
        )}
        {blacklistNotice && (
          <p className="fraud-page__notice" role="status">
            {blacklistNotice}
          </p>
        )}

        <div className="fraud-table-wrap">
          <table className="fraud-table">
            <thead>
              <tr>
                <th>Tipo</th>
                <th>Valor</th>
                <th>Motivo</th>
                <th>Creada</th>
                <th>
                  <span className="sr-only">Acciones</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {blacklistLoading ? (
                <tr>
                  <td colSpan={5} className="fraud-table__empty">
                    Cargando lista negra…
                  </td>
                </tr>
              ) : blacklist.length === 0 ? (
                <tr>
                  <td colSpan={5} className="fraud-table__empty">
                    Todavía no hay entradas en la lista negra.
                  </td>
                </tr>
              ) : (
                blacklist.map((entry) => (
                  <tr key={entry.id}>
                    <td>{entry.entry_type === "phone" ? "Teléfono" : "IP"}</td>
                    <td className="fraud-table__data">{entry.value_normalized}</td>
                    <td>{entry.reason}</td>
                    <td className="fraud-table__data">
                      {DATE_FORMATTER.format(new Date(entry.created_at))}
                    </td>
                    <td className="fraud-table__actions">
                      {confirmDeleteBlacklistId === entry.id ? (
                        <span className="fraud-table__actions-row">
                          <button
                            type="button"
                            className="fraud-table__action fraud-table__action--danger"
                            disabled={blacklistBusy}
                            onClick={() => void handleRemoveBlacklistEntry(entry.id)}
                          >
                            Confirmar
                          </button>
                          <button
                            type="button"
                            className="fraud-table__action"
                            onClick={() => setConfirmDeleteBlacklistId(null)}
                          >
                            Cancelar
                          </button>
                        </span>
                      ) : (
                        <button
                          type="button"
                          className="fraud-table__action"
                          disabled={blacklistBusy}
                          onClick={() => setConfirmDeleteBlacklistId(entry.id)}
                        >
                          Eliminar
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <form className="fraud-form" onSubmit={handleAddBlacklistEntry}>
          <div className="fraud-field">
            <label className="fraud-field__label" htmlFor="blacklist-entry-type">
              Tipo
            </label>
            <select
              id="blacklist-entry-type"
              className="fraud-field__input"
              value={newEntryType}
              aria-describedby={
                blacklistFieldErrors.entry_type ? "blacklist-entry-type-error" : undefined
              }
              onChange={(event) => setNewEntryType(event.target.value as "phone" | "ip")}
            >
              <option value="phone">Teléfono</option>
              <option value="ip">Dirección IP</option>
            </select>
            {blacklistFieldErrors.entry_type && (
              <p className="fraud-field__error" id="blacklist-entry-type-error" role="alert">
                {blacklistFieldErrors.entry_type}
              </p>
            )}
          </div>

          <div className="fraud-field">
            <label className="fraud-field__label" htmlFor="blacklist-value">
              Valor
            </label>
            <input
              id="blacklist-value"
              className="fraud-field__input"
              type="text"
              value={newEntryValue}
              placeholder={newEntryType === "phone" ? "300 123 4567" : "203.0.113.5"}
              aria-describedby={
                blacklistFieldErrors.value_normalized ? "blacklist-value-error" : undefined
              }
              aria-invalid={blacklistFieldErrors.value_normalized ? true : undefined}
              onChange={(event) => setNewEntryValue(event.target.value)}
            />
            {blacklistFieldErrors.value_normalized && (
              <p className="fraud-field__error" id="blacklist-value-error" role="alert">
                {blacklistFieldErrors.value_normalized}
              </p>
            )}
          </div>

          <div className="fraud-field">
            <label className="fraud-field__label" htmlFor="blacklist-reason">
              Motivo (1-500 caracteres)
            </label>
            <input
              id="blacklist-reason"
              className="fraud-field__input"
              type="text"
              maxLength={500}
              value={newEntryReason}
              aria-describedby={
                blacklistFieldErrors.reason ? "blacklist-reason-error" : undefined
              }
              aria-invalid={blacklistFieldErrors.reason ? true : undefined}
              onChange={(event) => setNewEntryReason(event.target.value)}
            />
            {blacklistFieldErrors.reason && (
              <p className="fraud-field__error" id="blacklist-reason-error" role="alert">
                {blacklistFieldErrors.reason}
              </p>
            )}
          </div>

          <button
            type="submit"
            className="fraud-table__action fraud-table__action--primary"
            disabled={blacklistBusy}
          >
            Agregar a la lista negra
          </button>
        </form>
      </section>

      <section className="fraud-panel" aria-labelledby="geoip-heading">
        <h2 className="fraud-panel__title" id="geoip-heading">
          Reglas GeoIP
        </h2>

        {geoipError && (
          <p className="fraud-page__error" role="alert">
            {geoipError}
          </p>
        )}
        {geoipNotice && (
          <p className="fraud-page__notice" role="status">
            {geoipNotice}
          </p>
        )}

        <div className="fraud-table-wrap">
          <table className="fraud-table">
            <thead>
              <tr>
                <th>Código</th>
                <th>Acción</th>
                <th>Habilitada</th>
                <th>Actualizada</th>
                <th>
                  <span className="sr-only">Acciones</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {geoipLoading ? (
                <tr>
                  <td colSpan={5} className="fraud-table__empty">
                    Cargando reglas GeoIP…
                  </td>
                </tr>
              ) : geoipRules.length === 0 ? (
                <tr>
                  <td colSpan={5} className="fraud-table__empty">
                    Todavía no hay reglas GeoIP.
                  </td>
                </tr>
              ) : (
                geoipRules.map((rule) => (
                  <tr key={rule.id}>
                    <td className="fraud-table__data">{rule.location_code}</td>
                    <td>{rule.action === "flag" ? "Marcar" : "Bloquear"}</td>
                    <td>
                      <button
                        type="button"
                        className="fraud-table__action"
                        disabled={geoipBusy}
                        onClick={() => void handleToggleGeoIpRule(rule)}
                      >
                        {rule.enabled ? "Habilitada" : "Deshabilitada"}
                      </button>
                    </td>
                    <td className="fraud-table__data">
                      {DATE_FORMATTER.format(new Date(rule.updated_at))}
                    </td>
                    <td className="fraud-table__actions">
                      {confirmDeleteGeoipId === rule.id ? (
                        <span className="fraud-table__actions-row">
                          <button
                            type="button"
                            className="fraud-table__action fraud-table__action--danger"
                            disabled={geoipBusy}
                            onClick={() => void handleDeleteGeoIpRule(rule.id)}
                          >
                            Confirmar
                          </button>
                          <button
                            type="button"
                            className="fraud-table__action"
                            onClick={() => setConfirmDeleteGeoipId(null)}
                          >
                            Cancelar
                          </button>
                        </span>
                      ) : (
                        <button
                          type="button"
                          className="fraud-table__action"
                          disabled={geoipBusy}
                          onClick={() => setConfirmDeleteGeoipId(rule.id)}
                        >
                          Eliminar
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <form className="fraud-form" onSubmit={handleAddGeoIpRule}>
          <div className="fraud-field">
            <label className="fraud-field__label" htmlFor="geoip-location-code">
              Código de ubicación (2-10 caracteres, se guarda en mayúsculas)
            </label>
            <input
              id="geoip-location-code"
              className="fraud-field__input"
              type="text"
              maxLength={10}
              value={newLocationCode}
              placeholder="CO o CO-DC"
              aria-describedby={
                geoipFieldErrors.location_code ? "geoip-location-code-error" : undefined
              }
              aria-invalid={geoipFieldErrors.location_code ? true : undefined}
              onChange={(event) => setNewLocationCode(event.target.value)}
            />
            {geoipFieldErrors.location_code && (
              <p className="fraud-field__error" id="geoip-location-code-error" role="alert">
                {geoipFieldErrors.location_code}
              </p>
            )}
          </div>

          <div className="fraud-field">
            <label className="fraud-field__label" htmlFor="geoip-action">
              Acción
            </label>
            <select
              id="geoip-action"
              className="fraud-field__input"
              value={newAction}
              aria-describedby={geoipFieldErrors.action ? "geoip-action-error" : undefined}
              onChange={(event) => setNewAction(event.target.value as "flag" | "block")}
            >
              <option value="flag">Marcar (flag)</option>
              <option value="block">Bloquear (block)</option>
            </select>
            {geoipFieldErrors.action && (
              <p className="fraud-field__error" id="geoip-action-error" role="alert">
                {geoipFieldErrors.action}
              </p>
            )}
          </div>

          <button
            type="submit"
            className="fraud-table__action fraud-table__action--primary"
            disabled={geoipBusy}
          >
            Crear regla
          </button>
        </form>
      </section>
    </div>
  );
}
