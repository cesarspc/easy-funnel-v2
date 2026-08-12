/**
 * Landing configuration templates in the dashboard: save one, apply one.
 *
 * The merchant runs unrelated products through the same funnel shape, so the
 * expensive part of a new landing is re-entering configuration that already
 * converts. These two controls make that a two-click operation.
 *
 * `SaveTemplateControl` closes the configuration section — the point at which
 * the merchant has just finished tuning a funnel is the point at which they
 * know it is worth keeping. `LoadTemplateDialog` sits in the page header next
 * to the publication control, because applying a template is a decision about
 * the whole page rather than an edit to one field.
 *
 * **The banner-count precondition is shown, not just enforced.** Every template
 * in the list states how many banners it needs and whether this landing
 * qualifies, and templates that do not fit are visibly disabled with the reason
 * attached. Letting the merchant pick one and then rejecting it would be a
 * worse version of the same information. The server re-checks regardless, and
 * its message is surfaced verbatim if it ever disagrees.
 */

import { useCallback, useEffect, useState, type JSX } from "react";
import { Modal } from "../../components/Modal";
import { ApiError, landingTemplatesApi, landingsApi } from "../../api";
import type { LandingDetail, LandingTemplate } from "../../api";

const MAX_TEMPLATE_NAME_LENGTH = 80;

function bannerWord(count: number): string {
  return count === 1 ? "banner" : "banners";
}

export interface SaveTemplateControlProps {
  landingId: number;
  /** Banner count shown in the hint, so the merchant knows what they are locking in. */
  bannerCount: number;
  disabled?: boolean;
}

/**
 * Name-and-save control for the current landing's configuration.
 *
 * A name collision is a 409 from the server rather than a silent overwrite, so
 * this asks before replacing: a template is deliberate work, and a repeated name
 * is at least as likely to be a typo as an intended update.
 */
export function SaveTemplateControl({
  landingId,
  bannerCount,
  disabled = false,
}: SaveTemplateControlProps): JSX.Element {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmOverwrite, setConfirmOverwrite] = useState(false);

  async function save(overwrite: boolean) {
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const saved = await landingTemplatesApi.save({
        landing_id: landingId,
        name,
        overwrite,
      });
      setNotice(
        overwrite
          ? `Plantilla «${saved.name}» actualizada.`
          : `Plantilla «${saved.name}» guardada.`,
      );
      setName("");
      setConfirmOverwrite(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // The name exists. Ask instead of deciding for them.
        setConfirmOverwrite(true);
        setError(err.message);
      } else {
        setConfirmOverwrite(false);
        setError(
          err instanceof ApiError ? err.message : "No se pudo guardar la plantilla.",
        );
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="landings-field" data-testid="save-template">
      <label className="landings-field__label" htmlFor="save-template-name">
        Guardar esta configuración como plantilla
      </label>
      <div className="lblocks__row">
        <input
          id="save-template-name"
          className="landings-field__input"
          value={name}
          maxLength={MAX_TEMPLATE_NAME_LENGTH}
          placeholder="Ej: Suplementos — 5 banners"
          aria-describedby="save-template-hint"
          aria-invalid={error ? true : undefined}
          onChange={(event) => {
            setName(event.target.value);
            setConfirmOverwrite(false);
            setError(null);
          }}
        />
        {confirmOverwrite ? (
          <>
            <button
              type="button"
              className="landings-table__action landings-table__action--danger"
              disabled={busy}
              onClick={() => void save(true)}
            >
              Reemplazar
            </button>
            <button
              type="button"
              className="landings-table__action"
              disabled={busy}
              onClick={() => {
                setConfirmOverwrite(false);
                setError(null);
              }}
            >
              Cancelar
            </button>
          </>
        ) : (
          <button
            type="button"
            className="landings-table__action"
            disabled={busy || disabled || !name.trim()}
            onClick={() => void save(false)}
          >
            Guardar plantilla
          </button>
        )}
      </div>
      <p className="landings-page__muted" id="save-template-hint">
        Guarda el CTA, el formulario, las ofertas, los colores y los componentes de
        conversión. No guarda las imágenes: la plantilla solo se podrá aplicar a
        landings con {bannerCount} {bannerWord(bannerCount)}.
      </p>
      {error && (
        <p className="landings-field__error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="landings-page__notice" role="status">
          {notice}
        </p>
      )}
    </div>
  );
}

export interface LoadTemplateDialogProps {
  landingId: number;
  /** The landing's current banner count, checked against each template's. */
  bannerCount: number;
  /** Called with the updated landing after a template is applied. */
  onLoaded: (detail: LandingDetail) => void;
  disabled?: boolean;
}

/**
 * Header button plus the template picker it opens.
 *
 * Templates are fetched when the dialog opens rather than on mount: the list is
 * only ever read here, and a landing editor session usually never opens it.
 */
export function LoadTemplateDialog({
  landingId,
  bannerCount,
  onLoaded,
  disabled = false,
}: LoadTemplateDialogProps): JSX.Element {
  const [open, setOpen] = useState(false);
  const [templates, setTemplates] = useState<LandingTemplate[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await landingTemplatesApi.list();
      setTemplates(response.templates);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "No se pudieron cargar las plantillas.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  function close() {
    setOpen(false);
    setSelectedId(null);
    setError(null);
  }

  async function apply() {
    if (selectedId === null) return;
    setError(null);
    setBusy(true);
    try {
      const detail = await landingsApi.loadTemplate(landingId, selectedId);
      onLoaded(detail);
      close();
    } catch (err) {
      // A 422 here carries the server's banner-count message, which names both
      // the required and the actual count.
      setError(err instanceof ApiError ? err.message : "No se pudo cargar la plantilla.");
    } finally {
      setBusy(false);
    }
  }

  const selected = templates.find((template) => template.id === selectedId) ?? null;
  const selectedFits = selected !== null && selected.banner_count === bannerCount;

  return (
    <>
      <button
        type="button"
        className="landings-table__action"
        disabled={disabled}
        onClick={() => setOpen(true)}
      >
        Cargar plantilla
      </button>

      <Modal
        isOpen={open}
        onClose={close}
        title="Cargar plantilla"
        subtitle={`Esta landing tiene ${bannerCount} ${bannerWord(bannerCount)}. Solo se pueden aplicar plantillas guardadas con esa misma cantidad.`}
      >
        {loading ? (
          <p className="landings-page__muted">Cargando plantillas…</p>
        ) : templates.length === 0 ? (
          <p className="landings-page__muted">
            Todavía no hay plantillas guardadas. Guarda una desde la configuración de
            cualquier landing.
          </p>
        ) : (
          <ul className="ltemplates__list" aria-label="Plantillas guardadas">
            {templates.map((template) => {
              const fits = template.banner_count === bannerCount;
              const inputId = `template-option-${template.id}`;
              const reasonId = `template-reason-${template.id}`;
              return (
                <li className="ltemplates__item" key={template.id}>
                  <input
                    type="radio"
                    id={inputId}
                    name="landing-template"
                    className="ltemplates__radio"
                    value={template.id}
                    disabled={!fits}
                    checked={selectedId === template.id}
                    aria-describedby={reasonId}
                    onChange={() => setSelectedId(template.id)}
                  />
                  <label className="ltemplates__label" htmlFor={inputId}>
                    <span className="ltemplates__name">{template.name}</span>
                    <span className="ltemplates__meta" id={reasonId}>
                      {template.banner_count} {bannerWord(template.banner_count)} ·{" "}
                      {template.block_count}{" "}
                      {template.block_count === 1 ? "componente" : "componentes"}
                      {fits ? "" : ` · no aplica a ${bannerCount} ${bannerWord(bannerCount)}`}
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
        )}

        {error && (
          <p className="landings-field__error" role="alert">
            {error}
          </p>
        )}

        <p className="landings-page__muted">
          Se reemplazan el CTA, el formulario, las ofertas, los colores y todos los
          componentes de conversión de esta landing. Las imágenes, el slug y el estado de
          publicación no cambian.
        </p>

        <div className="ltemplates__actions">
          <button
            type="button"
            className="landings-table__action landings-table__action--primary"
            disabled={busy || !selectedFits}
            onClick={() => void apply()}
          >
            {busy ? "Cargando…" : "Cargar plantilla"}
          </button>
          <button type="button" className="landings-table__action" onClick={close}>
            Cancelar
          </button>
        </div>
      </Modal>
    </>
  );
}
