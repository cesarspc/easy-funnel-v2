/**
 * Landing editor (Requirement 8.3, 8.19, 8.20): banner upload/removal/order
 * and alternative text, slug, CTA placement mode, COD form presentation, the
 * conversion components placed between rendered elements (Requirements
 * 3.27-3.31, in `LandingBlocksPanel`), and publish/unpublish controls for one
 * landing.
 *
 * Every field-specific backend error (`{field, message}`) is bound to the
 * control that produced it through `aria-describedby` and announced with
 * `role="alert"` (Requirement 8.19). All controls are native buttons, inputs,
 * and selects so keyboard focus and activation come for free (Requirement 8.20).
 */

import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { StatusPill } from "../../components";
import type {
  CtaBandStyle,
  CtaMode,
  FormPresentation,
  LandingBanner,
  LandingDetail,
  LandingOffer,
} from "../../api";
import { ApiError, landingsApi } from "../../api";
import { LandingBlocksPanel } from "./LandingBlocksPanel";
import "./LandingsPage.css";

const MAX_BANNERS = 15;

/** The form presents at most three quantity offers (see the Landing model). */
const OFFER_COUNT_CHOICES = [1, 2, 3] as const;

/**
 * One offer row as the editor holds it. Numbers stay strings while the merchant
 * types so a half-typed value never becomes `NaN`; they are parsed on submit.
 */
interface OfferForm {
  quantity: number;
  label: string;
  sublabel: string;
  discountPercent: string;
  compareAtPrice: string;
}

interface ConfigForm {
  slug: string;
  ctaMode: CtaMode;
  ctaInterval: string;
  ctaPositions: string;
  formPresentation: FormPresentation;
  ctaBandStyle: CtaBandStyle;
  accentColor: string;
  offerCount: number;
  offers: OfferForm[];
}

function toOfferForm(offer: LandingOffer): OfferForm {
  return {
    quantity: offer.quantity,
    label: offer.label,
    sublabel: offer.sublabel ?? "",
    discountPercent: offer.discount_percent ? String(offer.discount_percent) : "",
    compareAtPrice: offer.compare_at_price === null ? "" : String(offer.compare_at_price),
  };
}

/** Default copy for a quantity the merchant just exposed by raising the count. */
function blankOfferForm(quantity: number): OfferForm {
  return {
    quantity,
    label: quantity === 1 ? "1 unidad" : `${quantity} unidades`,
    sublabel: "",
    discountPercent: "",
    compareAtPrice: "",
  };
}

/**
 * Resize the offer rows to `count`, keeping whatever the merchant already wrote
 * for the quantities that survive. Lowering the count hides the trailing rows
 * rather than clearing them on the way down, which is why the previous rows are
 * consulted before falling back to defaults.
 */
function fitOffers(existing: OfferForm[], count: number): OfferForm[] {
  return Array.from({ length: count }, (_, index) => {
    const quantity = index + 1;
    return existing.find((offer) => offer.quantity === quantity) ?? blankOfferForm(quantity);
  });
}

function toConfigForm(landing: LandingDetail): ConfigForm {
  return {
    slug: landing.slug,
    ctaMode: landing.cta_mode,
    ctaInterval: landing.cta_interval === null ? "" : String(landing.cta_interval),
    ctaPositions: landing.cta_positions.join(", "),
    formPresentation: landing.form_presentation,
    ctaBandStyle: landing.cta_band_style ?? "gradient",
    accentColor: landing.accent_color ?? "#1a7a4c",
    offerCount: landing.offer_count,
    offers: fitOffers((landing.offers ?? []).map(toOfferForm), landing.offer_count),
  };
}

function parsePositions(raw: string): number[] {
  return raw
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part.length > 0)
    .map((part) => Number(part));
}

/** Smallest JPEG candidate, used for the admin thumbnail. */
function thumbnailUrl(banner: LandingBanner): string | null {
  const jpeg = banner.variants
    .filter((variant) => variant.format === "jpeg")
    .sort((a, b) => a.width - b.width);
  return jpeg[0]?.url ?? banner.variants[0]?.url ?? null;
}

export function LandingEditorPage() {
  const { landingId } = useParams<{ landingId: string }>();
  const id = Number(landingId);

  const [landing, setLanding] = useState<LandingDetail | null>(null);
  const [banners, setBanners] = useState<LandingBanner[]>([]);
  const [config, setConfig] = useState<ConfigForm | null>(null);
  const [altTextDrafts, setAltTextDrafts] = useState<Record<number, string>>({});
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [uploadAltText, setUploadAltText] = useState("");
  const [brokenPreviews, setBrokenPreviews] = useState<number[]>([]);

  const applyDetail = useCallback((detail: LandingDetail) => {
    setLanding(detail);
    setBanners(detail.banners);
    setConfig(toConfigForm(detail));
    setAltTextDrafts(
      Object.fromEntries(detail.banners.map((banner) => [banner.id, banner.alt_text])),
    );
  }, []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    landingsApi
      .get(id)
      .then((detail) => {
        if (active) applyDetail(detail);
      })
      .catch((err) => {
        if (active) {
          setError(err instanceof ApiError ? err.message : "No se pudo cargar la landing.");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [id, applyDetail]);

  function resetMessages() {
    setError(null);
    setNotice(null);
    setFieldErrors({});
  }

  function handleFailure(err: unknown, fallback: string) {
    if (err instanceof ApiError) {
      setError(err.message);
      if (err.fieldErrors) setFieldErrors(err.fieldErrors);
    } else {
      setError(fallback);
    }
  }

  function applyBanners(next: LandingBanner[]) {
    setBanners(next);
    setAltTextDrafts(Object.fromEntries(next.map((banner) => [banner.id, banner.alt_text])));
    setLanding((current) =>
      current ? { ...current, banners: next, banner_count: next.length } : current,
    );
  }

  async function handleUpload(event: React.FormEvent) {
    event.preventDefault();
    resetMessages();
    if (!file) {
      setFieldErrors({ file: "Selecciona una imagen JPEG, PNG o WebP." });
      return;
    }
    setBusy(true);
    try {
      await landingsApi.uploadBanner(id, file, uploadAltText);
      const detail = await landingsApi.get(id);
      applyDetail(detail);
      setFile(null);
      setUploadAltText("");
      setNotice("Banner subido.");
    } catch (err) {
      handleFailure(err, "No se pudo subir el banner.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveAltText(bannerId: number) {
    resetMessages();
    setBusy(true);
    try {
      const response = await landingsApi.updateBanner(id, bannerId, {
        alt_text: altTextDrafts[bannerId] ?? "",
      });
      applyBanners(response.banners);
      setNotice("Texto alternativo actualizado.");
    } catch (err) {
      handleFailure(err, "No se pudo actualizar el texto alternativo.");
    } finally {
      setBusy(false);
    }
  }

  async function handleMove(bannerId: number, direction: -1 | 1) {
    resetMessages();
    const current = banners.findIndex((banner) => banner.id === bannerId);
    const target = current + direction;
    if (current < 0 || target < 0 || target >= banners.length) return;
    setBusy(true);
    try {
      const response = await landingsApi.updateBanner(id, bannerId, { order_index: target });
      applyBanners(response.banners);
    } catch (err) {
      handleFailure(err, "No se pudo cambiar el orden del banner.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(bannerId: number) {
    resetMessages();
    setBusy(true);
    try {
      const response = await landingsApi.deleteBanner(id, bannerId);
      applyBanners(response.banners);
      setNotice("Banner eliminado.");
    } catch (err) {
      handleFailure(err, "No se pudo eliminar el banner.");
    } finally {
      setBusy(false);
      setConfirmDeleteId(null);
    }
  }

  async function handleSaveConfig(event: React.FormEvent) {
    event.preventDefault();
    if (!config) return;
    resetMessages();
    setBusy(true);
    try {
      const detail = await landingsApi.updateConfig(id, {
        slug: config.slug,
        cta_mode: config.ctaMode,
        cta_interval: config.ctaMode === "every_n" ? Number(config.ctaInterval) : null,
        cta_positions:
          config.ctaMode === "fixed_positions" ? parsePositions(config.ctaPositions) : [],
        form_presentation: config.formPresentation,
        cta_band_style: config.ctaBandStyle,
        accent_color: config.accentColor,
        offer_count: config.offerCount,
        // Only the rows the merchant can actually see are sent, so lowering the
        // count drops the trailing offers instead of submitting copy for tiers
        // the form no longer shows.
        offers: config.offers.slice(0, config.offerCount).map((offer) => ({
          quantity: offer.quantity,
          label: offer.label,
          // Empty string is meaningful: it turns the sub-text off.
          sublabel: offer.sublabel.trim() === "" ? "" : offer.sublabel,
          discount_percent:
            offer.discountPercent.trim() === "" ? null : Number(offer.discountPercent),
          compare_at_price:
            offer.compareAtPrice.trim() === "" ? null : Number(offer.compareAtPrice),
        })),
      });
      applyDetail(detail);
      setNotice("Configuración guardada.");
    } catch (err) {
      handleFailure(err, "No se pudo guardar la configuración.");
    } finally {
      setBusy(false);
    }
  }

  async function handlePublicationChange(publish: boolean) {
    resetMessages();
    setBusy(true);
    try {
      const detail = publish ? await landingsApi.publish(id) : await landingsApi.unpublish(id);
      applyDetail(detail);
      setNotice(publish ? "Landing publicada." : "Landing en borrador.");
    } catch (err) {
      handleFailure(err, "No se pudo cambiar el estado de publicación.");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <p className="landings-page__muted">Cargando landing…</p>;
  }

  if (!landing || !config) {
    return (
      <div className="landings-page">
        <p className="landings-page__error" role="alert">
          {error ?? "Landing no encontrada."}
        </p>
        <Link className="landings-table__action" to="/admin/landings">
          Volver a landings
        </Link>
      </div>
    );
  }

  return (
    <div className="landings-page">
      <div className="landings-page__header">
        <div>
          <h1 className="landings-page__title">{landing.product_name}</h1>
          <p className="landings-page__subtitle">
            <StatusPill status={landing.status} /> <span>/p/{landing.slug}</span>
          </p>
        </div>
        <div className="landings-page__header-actions">
          {landing.status === "draft" ? (
            <button
              type="button"
              className="landings-table__action landings-table__action--primary"
              disabled={busy}
              onClick={() => void handlePublicationChange(true)}
            >
              Publicar
            </button>
          ) : (
            <button
              type="button"
              className="landings-table__action"
              disabled={busy}
              onClick={() => void handlePublicationChange(false)}
            >
              Despublicar
            </button>
          )}
          <Link className="landings-table__action" to="/admin/landings">
            Volver
          </Link>
        </div>
      </div>

      {error && (
        <p className="landings-page__error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="landings-page__notice" role="status">
          {notice}
        </p>
      )}

      <section className="landings-panel" aria-labelledby="banners-heading">
        <h2 className="landings-panel__title" id="banners-heading">
          Banners ({banners.length}/{MAX_BANNERS})
        </h2>

        {banners.length === 0 ? (
          <p className="landings-page__muted">
            Sube al menos un banner para poder publicar la landing.
          </p>
        ) : (
          <ul className="banner-list">
            {banners.map((banner, index) => {
              const preview = thumbnailUrl(banner);
              const altFieldId = `alt-text-${banner.id}`;
              return (
                <li key={banner.id} className="banner-list__item">
                  <span className="banner-list__position" aria-hidden="true">
                    {index + 1}
                  </span>
                  {preview && !brokenPreviews.includes(banner.id) ? (
                    <img
                      className="banner-list__thumb"
                      src={preview}
                      alt={banner.alt_text}
                      width={96}
                      height={64}
                      loading="lazy"
                      onError={() => setBrokenPreviews((ids) => [...ids, banner.id])}
                    />
                  ) : (
                    <span className="banner-list__thumb banner-list__thumb--empty">
                      Sin previsualización
                    </span>
                  )}

                  <div className="banner-list__fields">
                    <label className="landings-field__label" htmlFor={altFieldId}>
                      Texto alternativo
                    </label>
                    <input
                      id={altFieldId}
                      className="landings-field__input"
                      type="text"
                      maxLength={200}
                      value={altTextDrafts[banner.id] ?? ""}
                      onChange={(event) =>
                        setAltTextDrafts((drafts) => ({
                          ...drafts,
                          [banner.id]: event.target.value,
                        }))
                      }
                    />
                  </div>

                  <div className="banner-list__actions">
                    <button
                      type="button"
                      className="landings-table__action"
                      disabled={busy || altTextDrafts[banner.id] === banner.alt_text}
                      onClick={() => void handleSaveAltText(banner.id)}
                    >
                      Guardar texto
                    </button>
                    <button
                      type="button"
                      className="landings-table__action"
                      disabled={busy || index === 0}
                      aria-label={`Subir banner ${index + 1}`}
                      onClick={() => void handleMove(banner.id, -1)}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      className="landings-table__action"
                      disabled={busy || index === banners.length - 1}
                      aria-label={`Bajar banner ${index + 1}`}
                      onClick={() => void handleMove(banner.id, 1)}
                    >
                      ↓
                    </button>
                    {confirmDeleteId === banner.id ? (
                      <>
                        <button
                          type="button"
                          className="landings-table__action landings-table__action--danger"
                          disabled={busy}
                          onClick={() => void handleDelete(banner.id)}
                        >
                          Confirmar
                        </button>
                        <button
                          type="button"
                          className="landings-table__action"
                          onClick={() => setConfirmDeleteId(null)}
                        >
                          Cancelar
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        className="landings-table__action"
                        disabled={busy}
                        onClick={() => setConfirmDeleteId(banner.id)}
                      >
                        Eliminar
                      </button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        <form className="landings-form" onSubmit={handleUpload}>
          <div className="landings-field">
            <label className="landings-field__label" htmlFor="banner-file">
              Imagen (JPEG, PNG o WebP, ancho 480-8000 px, máx. 10 MiB)
            </label>
            <input
              id="banner-file"
              className="landings-field__input"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              aria-describedby={fieldErrors.file ? "banner-file-error" : undefined}
              aria-invalid={fieldErrors.file ? true : undefined}
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
            {fieldErrors.file && (
              <p className="landings-field__error" id="banner-file-error" role="alert">
                {fieldErrors.file}
              </p>
            )}
          </div>

          <div className="landings-field">
            <label className="landings-field__label" htmlFor="banner-alt-text">
              Texto alternativo (1-200 caracteres)
            </label>
            <input
              id="banner-alt-text"
              className="landings-field__input"
              type="text"
              maxLength={200}
              value={uploadAltText}
              aria-describedby={fieldErrors.alt_text ? "banner-alt-text-error" : undefined}
              aria-invalid={fieldErrors.alt_text ? true : undefined}
              onChange={(event) => setUploadAltText(event.target.value)}
            />
            {fieldErrors.alt_text && (
              <p className="landings-field__error" id="banner-alt-text-error" role="alert">
                {fieldErrors.alt_text}
              </p>
            )}
          </div>

          <button
            type="submit"
            className="landings-table__action landings-table__action--primary"
            disabled={busy || banners.length >= MAX_BANNERS}
          >
            Subir banner
          </button>
          {banners.length >= MAX_BANNERS && (
            <p className="landings-page__muted">
              Una landing admite como máximo {MAX_BANNERS} banners.
            </p>
          )}
        </form>
      </section>

      <section className="landings-panel" aria-labelledby="config-heading">
        <h2 className="landings-panel__title" id="config-heading">
          Configuración
        </h2>

        <form className="landings-form" onSubmit={handleSaveConfig}>
          <div className="landings-field">
            <label className="landings-field__label" htmlFor="landing-slug">
              Slug público
            </label>
            <input
              id="landing-slug"
              className="landings-field__input"
              type="text"
              value={config.slug}
              aria-describedby={fieldErrors.slug ? "landing-slug-error" : undefined}
              aria-invalid={fieldErrors.slug ? true : undefined}
              onChange={(event) =>
                setConfig((current) => (current ? { ...current, slug: event.target.value } : current))
              }
            />
            {fieldErrors.slug && (
              <p className="landings-field__error" id="landing-slug-error" role="alert">
                {fieldErrors.slug}
              </p>
            )}
          </div>

          <div className="landings-field">
            <label className="landings-field__label" htmlFor="landing-cta-mode">
              Ubicación de los CTA
            </label>
            <select
              id="landing-cta-mode"
              className="landings-field__input"
              value={config.ctaMode}
              aria-describedby={fieldErrors.cta_mode ? "landing-cta-mode-error" : undefined}
              onChange={(event) =>
                setConfig((current) =>
                  current ? { ...current, ctaMode: event.target.value as CtaMode } : current,
                )
              }
            >
              <option value="after_every">Después de cada banner</option>
              <option value="every_n">Cada N banners</option>
              <option value="fixed_positions">En posiciones fijas</option>
            </select>
            {fieldErrors.cta_mode && (
              <p className="landings-field__error" id="landing-cta-mode-error" role="alert">
                {fieldErrors.cta_mode}
              </p>
            )}
          </div>

          {config.ctaMode === "every_n" && (
            <div className="landings-field">
              <label className="landings-field__label" htmlFor="landing-cta-interval">
                Intervalo (1-15)
              </label>
              <input
                id="landing-cta-interval"
                className="landings-field__input"
                type="number"
                min={1}
                max={15}
                value={config.ctaInterval}
                aria-describedby={
                  fieldErrors.cta_interval ? "landing-cta-interval-error" : undefined
                }
                aria-invalid={fieldErrors.cta_interval ? true : undefined}
                onChange={(event) =>
                  setConfig((current) =>
                    current ? { ...current, ctaInterval: event.target.value } : current,
                  )
                }
              />
              {fieldErrors.cta_interval && (
                <p className="landings-field__error" id="landing-cta-interval-error" role="alert">
                  {fieldErrors.cta_interval}
                </p>
              )}
            </div>
          )}

          {config.ctaMode === "fixed_positions" && (
            <div className="landings-field">
              <label className="landings-field__label" htmlFor="landing-cta-positions">
                Posiciones (separadas por comas, p. ej. 1, 3)
              </label>
              <input
                id="landing-cta-positions"
                className="landings-field__input"
                type="text"
                value={config.ctaPositions}
                aria-describedby={
                  fieldErrors.cta_positions ? "landing-cta-positions-error" : undefined
                }
                aria-invalid={fieldErrors.cta_positions ? true : undefined}
                onChange={(event) =>
                  setConfig((current) =>
                    current ? { ...current, ctaPositions: event.target.value } : current,
                  )
                }
              />
              {fieldErrors.cta_positions && (
                <p className="landings-field__error" id="landing-cta-positions-error" role="alert">
                  {fieldErrors.cta_positions}
                </p>
              )}
            </div>
          )}

          <div className="landings-field">
            <label className="landings-field__label" htmlFor="landing-cta-band-style">
              Fondo del botón CTA
            </label>
            <select
              id="landing-cta-band-style"
              className="landings-field__input"
              value={config.ctaBandStyle}
              aria-describedby={
                fieldErrors.cta_band_style
                  ? "landing-cta-band-style-error landing-cta-band-style-hint"
                  : "landing-cta-band-style-hint"
              }
              onChange={(event) =>
                setConfig((current) =>
                  current
                    ? { ...current, ctaBandStyle: event.target.value as CtaBandStyle }
                    : current,
                )
              }
            >
              <option value="gradient">Degradado entre banners</option>
              <option value="solid">Color plano</option>
            </select>
            <p className="landings-field__hint" id="landing-cta-band-style-hint">
              El degradado va del borde inferior del banner de arriba al borde superior del
              banner de abajo. El color plano usa el punto medio de esos dos bordes.
            </p>
            {fieldErrors.cta_band_style && (
              <p className="landings-field__error" id="landing-cta-band-style-error" role="alert">
                {fieldErrors.cta_band_style}
              </p>
            )}
          </div>

          {/* Accent color. One picker, not four: every other shade the public
              page needs (hover, tile tint, readable foreground) is derived from
              this server-side, so a merchant cannot land on white text over a
              pale button. The text input beside the swatch exists because a
              brand hex is usually pasted, not hunted for in a color wheel. */}
          <div className="landings-field">
            <label className="landings-field__label" htmlFor="landing-accent-color">
              Color de la landing
            </label>
            <div className="landings-field__color">
              <input
                id="landing-accent-color"
                className="landings-field__swatch"
                type="color"
                value={config.accentColor}
                aria-describedby={
                  fieldErrors.accent_color
                    ? "landing-accent-color-error landing-accent-color-hint"
                    : "landing-accent-color-hint"
                }
                aria-invalid={fieldErrors.accent_color ? true : undefined}
                onChange={(event) =>
                  setConfig((current) =>
                    current ? { ...current, accentColor: event.target.value } : current,
                  )
                }
              />
              <input
                className="landings-field__input landings-field__input--hex"
                type="text"
                value={config.accentColor}
                aria-label="Color de la landing en hexadecimal"
                spellCheck={false}
                maxLength={7}
                onChange={(event) =>
                  setConfig((current) =>
                    current ? { ...current, accentColor: event.target.value } : current,
                  )
                }
              />
            </div>
            <p className="landings-field__hint" id="landing-accent-color-hint">
              Se aplica al botón de CTA, los bordes y textos destacados, la oferta seleccionada y
              un tono claro de fondo en las ofertas. Los tonos de hover y el color de texto se
              calculan solos para que siempre haya contraste.
            </p>
            {fieldErrors.accent_color && (
              <p className="landings-field__error" id="landing-accent-color-error" role="alert">
                {fieldErrors.accent_color}
              </p>
            )}
          </div>

          {/* Quantity offers. The count drives how many rows render, so the
              merchant never edits copy for a tier the buyer will not see. */}
          <div className="landings-field">
            <label className="landings-field__label" htmlFor="landing-offer-count">
              Número de ofertas
            </label>
            <select
              id="landing-offer-count"
              className="landings-field__input"
              value={config.offerCount}
              aria-describedby={
                fieldErrors.offer_count
                  ? "landing-offer-count-error landing-offer-count-hint"
                  : "landing-offer-count-hint"
              }
              aria-invalid={fieldErrors.offer_count ? true : undefined}
              onChange={(event) => {
                const count = Number(event.target.value);
                setConfig((current) =>
                  current
                    ? { ...current, offerCount: count, offers: fitOffers(current.offers, count) }
                    : current,
                );
              }}
            >
              {OFFER_COUNT_CHOICES.map((count) => (
                <option key={count} value={count}>
                  {count === 1 ? "1 oferta" : `${count} ofertas`}
                </option>
              ))}
            </select>
            <p className="landings-field__hint" id="landing-offer-count-hint">
              Cuántas opciones de cantidad ve el comprador en el formulario.
            </p>
            {fieldErrors.offer_count && (
              <p className="landings-field__error" id="landing-offer-count-error" role="alert">
                {fieldErrors.offer_count}
              </p>
            )}
          </div>

          <fieldset className="landings-offers">
            <legend className="landings-offers__legend">Ofertas</legend>
            {fieldErrors.offers && (
              <p className="landings-field__error" id="landing-offers-error" role="alert">
                {fieldErrors.offers}
              </p>
            )}

            {config.offers.slice(0, config.offerCount).map((offer, index) => (
              <div className="landings-offer" key={offer.quantity}>
                <p className="landings-offer__quantity">
                  {offer.quantity === 1 ? "1 unidad" : `${offer.quantity} unidades`}
                </p>

                <div className="landings-field">
                  <label
                    className="landings-field__label"
                    htmlFor={`landing-offer-label-${offer.quantity}`}
                  >
                    Texto
                  </label>
                  <input
                    id={`landing-offer-label-${offer.quantity}`}
                    className="landings-field__input"
                    type="text"
                    value={offer.label}
                    maxLength={60}
                    aria-describedby={fieldErrors.offers ? "landing-offers-error" : undefined}
                    onChange={(event) =>
                      setConfig((current) =>
                        current
                          ? {
                              ...current,
                              offers: current.offers.map((item, itemIndex) =>
                                itemIndex === index
                                  ? { ...item, label: event.target.value }
                                  : item,
                              ),
                            }
                          : current,
                      )
                    }
                  />
                </div>

                <div className="landings-field">
                  <label
                    className="landings-field__label"
                    htmlFor={`landing-offer-sublabel-${offer.quantity}`}
                  >
                    Sub-texto (opcional)
                  </label>
                  <input
                    id={`landing-offer-sublabel-${offer.quantity}`}
                    className="landings-field__input"
                    type="text"
                    value={offer.sublabel}
                    maxLength={80}
                    aria-describedby={`landing-offer-sublabel-hint-${offer.quantity}`}
                    onChange={(event) =>
                      setConfig((current) =>
                        current
                          ? {
                              ...current,
                              offers: current.offers.map((item, itemIndex) =>
                                itemIndex === index
                                  ? { ...item, sublabel: event.target.value }
                                  : item,
                              ),
                            }
                          : current,
                      )
                    }
                  />
                  <p
                    className="landings-field__hint"
                    id={`landing-offer-sublabel-hint-${offer.quantity}`}
                  >
                    Déjalo vacío para que la oferta no muestre segunda línea.
                  </p>
                </div>

                {/* A single unit has no volume saving to show, so it gets an
                    informational reference price; two or three units get a real
                    percentage off. Offering both on one tier would let the page
                    advertise a discount off an invented "was" price. */}
                {offer.quantity === 1 ? (
                  <div className="landings-field">
                    <label
                      className="landings-field__label"
                      htmlFor={`landing-offer-compare-${offer.quantity}`}
                    >
                      Precio de comparación (opcional)
                    </label>
                    <input
                      id={`landing-offer-compare-${offer.quantity}`}
                      className="landings-field__input"
                      type="number"
                      min={0}
                      step="0.01"
                      inputMode="decimal"
                      value={offer.compareAtPrice}
                      aria-describedby={`landing-offer-compare-hint-${offer.quantity}`}
                      onChange={(event) =>
                        setConfig((current) =>
                          current
                            ? {
                                ...current,
                                offers: current.offers.map((item, itemIndex) =>
                                  itemIndex === index
                                    ? { ...item, compareAtPrice: event.target.value }
                                    : item,
                                ),
                              }
                            : current,
                        )
                      }
                    />
                    <p
                      className="landings-field__hint"
                      id={`landing-offer-compare-hint-${offer.quantity}`}
                    >
                      Solo informativo en la landing: se muestra tachado junto al precio. No
                      cambia lo que paga el comprador.
                    </p>
                  </div>
                ) : (
                  <div className="landings-field">
                    <label
                      className="landings-field__label"
                      htmlFor={`landing-offer-discount-${offer.quantity}`}
                    >
                      Descuento (%)
                    </label>
                    <input
                      id={`landing-offer-discount-${offer.quantity}`}
                      className="landings-field__input"
                      type="number"
                      min={0}
                      max={90}
                      step={1}
                      inputMode="numeric"
                      value={offer.discountPercent}
                      aria-describedby={`landing-offer-discount-hint-${offer.quantity}`}
                      onChange={(event) =>
                        setConfig((current) =>
                          current
                            ? {
                                ...current,
                                offers: current.offers.map((item, itemIndex) =>
                                  itemIndex === index
                                    ? { ...item, discountPercent: event.target.value }
                                    : item,
                                ),
                              }
                            : current,
                        )
                      }
                    />
                    <p
                      className="landings-field__hint"
                      id={`landing-offer-discount-hint-${offer.quantity}`}
                    >
                      Reduce de verdad el total de esta oferta y queda registrado en el pedido.
                      Máximo 90%.
                    </p>
                  </div>
                )}
              </div>
            ))}
          </fieldset>

          <div className="landings-field">
            <label className="landings-field__label" htmlFor="landing-form-presentation">
              Formulario COD
            </label>
            <select
              id="landing-form-presentation"
              className="landings-field__input"
              value={config.formPresentation}
              aria-describedby={
                fieldErrors.form_presentation ? "landing-form-presentation-error" : undefined
              }
              onChange={(event) =>
                setConfig((current) =>
                  current
                    ? { ...current, formPresentation: event.target.value as FormPresentation }
                    : current,
                )
              }
            >
              <option value="inline">En la página</option>
              <option value="modal">En ventana modal</option>
            </select>
            {fieldErrors.form_presentation && (
              <p
                className="landings-field__error"
                id="landing-form-presentation-error"
                role="alert"
              >
                {fieldErrors.form_presentation}
              </p>
            )}
          </div>

          <button
            type="submit"
            className="landings-table__action landings-table__action--primary"
            disabled={busy}
          >
            Guardar configuración
          </button>
          {fieldErrors.banners && (
            <p className="landings-field__error" role="alert">
              {fieldErrors.banners}
            </p>
          )}
        </form>

        <p className="landings-page__muted">
          CTA después de los banners: {landing.resolved_cta_positions.join(", ") || "ninguno"}
        </p>
      </section>

      <LandingBlocksPanel
        landingId={landing.id}
        sequenceSignature={`${banners.length}:${landing.resolved_cta_positions.join(",")}`}
      />
    </div>
  );
}
