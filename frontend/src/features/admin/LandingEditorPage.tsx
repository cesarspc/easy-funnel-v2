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
  CtaColorMode,
  CtaMode,
  FormPresentation,
  LandingBanner,
  LandingDetail,
  LandingOffer,
} from "../../api";
import { ApiError, landingsApi } from "../../api";
import { LandingBlocksPanel } from "./LandingBlocksPanel";
import { LoadTemplateDialog, SaveTemplateControl } from "./LandingTemplates";
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
  discountAmount: string;
  calculatedDiscountPercent: number;
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
  formAccentColor: string;
  blocksAccentColor: string;
  offerCount: number;
  defaultOfferQuantity: number;
  offers: OfferForm[];
  ctaText: string;
  ctaAnimation: string;
  ctaTextOverrides: Record<string, string>;
  ctaColorModes: Record<string, Exclude<CtaColorMode, "default">>;
  blocksDarkMode: boolean;
}

function toOfferForm(offer: LandingOffer): OfferForm {
  return {
    quantity: offer.quantity,
    label: offer.label,
    sublabel: offer.sublabel ?? "",
    discountPercent: offer.discount_percent ? String(offer.discount_percent) : "",
    discountAmount:
      offer.discount_amount === null || offer.discount_amount === undefined
        ? ""
        : String(offer.discount_amount),
    calculatedDiscountPercent:
      offer.calculated_discount_percent ?? offer.discount_percent ?? 0,
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
    discountAmount: "",
    calculatedDiscountPercent: 0,
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
    formAccentColor: landing.form_accent_color ?? "",
    blocksAccentColor: landing.blocks_accent_color ?? "",
    offerCount: landing.offer_count,
    defaultOfferQuantity: landing.default_offer_quantity ?? 1,
    offers: fitOffers((landing.offers ?? []).map(toOfferForm), landing.offer_count),
    ctaText: landing.cta_text ?? "",
    ctaAnimation: landing.cta_animation ?? "",
    ctaTextOverrides: { ...(landing.cta_text_overrides ?? {}) },
    ctaColorModes: { ...(landing.cta_color_modes ?? {}) },
    blocksDarkMode: landing.blocks_dark_mode ?? false,
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
  /**
   * Bumped when a template is applied. Loading a template rewrites the
   * landing's conversion components, and the components panel reloads off its
   * `sequenceSignature` — which a template need not change (a template with the
   * same CTA layout produces the same signature). Without this the panel would
   * keep showing the components the template just replaced.
   */
  const [templateReloadToken, setTemplateReloadToken] = useState(0);

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
        // Empty is an explicit reset, not an omitted update. This prevents a
        // previously saved override from returning after refresh.
        form_accent_color: config.formAccentColor.trim(),
        blocks_accent_color: config.blocksAccentColor.trim(),
        offer_count: config.offerCount,
        default_offer_quantity: config.defaultOfferQuantity,
        cta_text: config.ctaText.trim() || null,
        cta_animation: (config.ctaAnimation as "slide" | "shake") || null,
        cta_text_overrides: config.ctaTextOverrides,
        cta_color_modes: config.ctaColorModes,
        blocks_dark_mode: config.blocksDarkMode,
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
          discount_amount:
            offer.discountAmount.trim() === "" ? null : Number(offer.discountAmount),
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
          <LoadTemplateDialog
            landingId={landing.id}
            bannerCount={banners.length}
            disabled={busy}
            onLoaded={(detail) => {
              applyDetail(detail);
              setTemplateReloadToken((token) => token + 1);
              resetMessages();
              setNotice("Plantilla cargada.");
            }}
          />
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

          {/* Form accent color. Separate from the CTA/page accent above: this
              themes the COD form alone (tier tiles, focus rings, submit
              button), so a merchant can, for example, keep a bold CTA button
              while the form itself stays neutral. Left blank, the form keeps
              following the CTA's accent — the picker below shows that fallback
              live rather than defaulting to a fixed color. */}
          <div className="landings-field">
            <label className="landings-field__label" htmlFor="landing-form-accent-color">
              Color del formulario
            </label>
            <div className="landings-field__color">
              <input
                id="landing-form-accent-color"
                className="landings-field__swatch"
                type="color"
                value={config.formAccentColor || config.accentColor}
                aria-describedby={
                  fieldErrors.form_accent_color
                    ? "landing-form-accent-color-error landing-form-accent-color-hint"
                    : "landing-form-accent-color-hint"
                }
                aria-invalid={fieldErrors.form_accent_color ? true : undefined}
                onChange={(event) =>
                  setConfig((current) =>
                    current ? { ...current, formAccentColor: event.target.value } : current,
                  )
                }
              />
              <input
                className="landings-field__input landings-field__input--hex"
                type="text"
                placeholder="Igual al color de la landing"
                value={config.formAccentColor}
                aria-label="Color del formulario en hexadecimal"
                spellCheck={false}
                maxLength={7}
                onChange={(event) =>
                  setConfig((current) =>
                    current ? { ...current, formAccentColor: event.target.value } : current,
                  )
                }
              />
              {config.formAccentColor && (
                <button
                  type="button"
                  className="landings-field__clear"
                  onClick={() =>
                    setConfig((current) =>
                      current ? { ...current, formAccentColor: "" } : current,
                    )
                  }
                >
                  Usar el color de la landing
                </button>
              )}
            </div>
            <p className="landings-field__hint" id="landing-form-accent-color-hint">
              Colorea solo el formulario de pedido (cantidades, bordes de foco, botón de
              confirmar). Déjalo vacío para que siga el color de la landing.
            </p>
            {fieldErrors.form_accent_color && (
              <p
                className="landings-field__error"
                id="landing-form-accent-color-error"
                role="alert"
              >
                {fieldErrors.form_accent_color}
              </p>
            )}
          </div>

          {/* Conversion-block default accent. */}
          <div className="landings-field">
            <label className="landings-field__label" htmlFor="landing-blocks-accent-color">
              Color de componentes
            </label>
            <div className="landings-field__color">
              <input
                id="landing-blocks-accent-color"
                className="landings-field__swatch"
                type="color"
                value={config.blocksAccentColor || config.formAccentColor || config.accentColor}
                aria-describedby="landing-blocks-accent-color-hint"
                aria-invalid={fieldErrors.blocks_accent_color ? true : undefined}
                onChange={(event) =>
                  setConfig((current) =>
                    current ? { ...current, blocksAccentColor: event.target.value } : current,
                  )
                }
              />
              <input
                className="landings-field__input landings-field__input--hex"
                type="text"
                placeholder="Igual al color del formulario"
                value={config.blocksAccentColor}
                aria-label="Color de componentes en hexadecimal"
                spellCheck={false}
                maxLength={7}
                onChange={(event) =>
                  setConfig((current) =>
                    current ? { ...current, blocksAccentColor: event.target.value } : current,
                  )
                }
              />
              {config.blocksAccentColor && (
                <button
                  type="button"
                  className="landings-field__clear"
                  onClick={() =>
                    setConfig((current) =>
                      current ? { ...current, blocksAccentColor: "" } : current,
                    )
                  }
                >
                  Usar el color del formulario
                </button>
              )}
            </div>
            <p className="landings-field__hint" id="landing-blocks-accent-color-hint">
              Es el color predeterminado de todos los componentes de conversión. Déjalo
              vacío para seguir el color del formulario; cada componente todavía puede
              sobrescribirlo individualmente.
            </p>
            {fieldErrors.blocks_accent_color && (
              <p className="landings-field__error" role="alert">
                {fieldErrors.blocks_accent_color}
              </p>
            )}
          </div>

          {/* Blocks dark mode global toggle */}
          <div className="landings-field">
            <label className="lblocks__checkbox-label">
              <input
                type="checkbox"
                checked={config.blocksDarkMode}
                onChange={(event) =>
                  setConfig((current) =>
                    current ? { ...current, blocksDarkMode: event.target.checked } : current,
                  )
                }
              />
              Componentes de conversión en modo oscuro
            </label>
            <p className="landings-field__hint">
              Fondo oscuro en todos los componentes de conversión. Los componentes individuales
              pueden sobreescribir este ajuste.
            </p>
          </div>

          {/* Quantity offers. The count drives how many rows render, so the
              merchant never edits copy for a tier the buyer will not see. */}
          <div className="landings-field">
            <label className="landings-field__label" htmlFor="landing-cta-text">
              Texto del botón CTA
            </label>
            <input
              id="landing-cta-text"
              className="landings-field__input"
              type="text"
              maxLength={60}
              placeholder="Pedir ahora — $precio (por defecto)"
              value={config.ctaText}
              aria-describedby={
                fieldErrors.cta_text
                  ? "landing-cta-text-error landing-cta-text-hint"
                  : "landing-cta-text-hint"
              }
              aria-invalid={fieldErrors.cta_text ? true : undefined}
              onChange={(event) =>
                setConfig((current) =>
                  current ? { ...current, ctaText: event.target.value } : current,
                )
              }
            />
            <p className="landings-field__hint" id="landing-cta-text-hint">
              Máximo 60 caracteres. Déjalo vacío para usar el texto por defecto con el precio.
            </p>
            {fieldErrors.cta_text && (
              <p className="landings-field__error" id="landing-cta-text-error" role="alert">
                {fieldErrors.cta_text}
              </p>
            )}
          </div>

          <div className="landings-field">
            <label className="landings-field__label" htmlFor="landing-cta-animation">
              Animación del botón CTA
            </label>
            <select
              id="landing-cta-animation"
              className="landings-field__input"
              value={config.ctaAnimation}
              aria-describedby={
                fieldErrors.cta_animation
                  ? "landing-cta-animation-error landing-cta-animation-hint"
                  : "landing-cta-animation-hint"
              }
              onChange={(event) =>
                setConfig((current) =>
                  current ? { ...current, ctaAnimation: event.target.value } : current,
                )
              }
            >
              <option value="">Sin animación</option>
              <option value="slide">Brillo (izquierda a derecha)</option>
              <option value="shake">Sacudir</option>
            </select>
            <p className="landings-field__hint" id="landing-cta-animation-hint">
              La animación se repite para llamar la atención. Se pausa al hacer hover.
            </p>
            {fieldErrors.cta_animation && (
              <p className="landings-field__error" id="landing-cta-animation-error" role="alert">
                {fieldErrors.cta_animation}
              </p>
            )}
          </div>

          {/* Per-CTA-position text override. Independent of `cta_text` above:
              this lets one specific CTA (e.g. only the second one) say
              something different — "Lo quiero ahora" — while every other CTA
              on the landing keeps showing the default label. Rows are keyed
              off `resolved_cta_positions`, the actual 1-based positions the
              current banner sequence renders a CTA at, so the merchant is
              never offered an override for a CTA that does not exist. */}
          {landing && landing.resolved_cta_positions.length > 0 && (
            <div className="landings-field">
              <label className="landings-field__label">Personalización por CTA</label>
              <p className="landings-field__hint" id="landing-cta-overrides-hint">
                Personaliza el texto y el fondo de cada posición. Predeterminado conserva el
                degradado o color medio calculado desde los banners.
              </p>
              <div className="landings-field__overrides">
                {landing.resolved_cta_positions.map((position) => {
                  const key = String(position);
                  const value = config.ctaTextOverrides[key] ?? "";
                  return (
                    <div key={position} className="landings-field__row">
                      <label
                        className="landings-field__label"
                        htmlFor={`landing-cta-override-${position}`}
                        style={{ minWidth: 90 }}
                      >
                        CTA #{position}
                      </label>
                      <input
                        id={`landing-cta-override-${position}`}
                        className="landings-field__input"
                        type="text"
                        maxLength={60}
                        placeholder="Usar el texto por defecto"
                        value={value}
                        onChange={(event) => {
                          const text = event.target.value;
                          setConfig((current) => {
                            if (!current) return current;
                            const next = { ...current.ctaTextOverrides };
                            if (text.trim() === "") {
                              delete next[key];
                            } else {
                              next[key] = text;
                            }
                            return { ...current, ctaTextOverrides: next };
                          });
                        }}
                      />
                      <select
                        className="landings-field__input landings-field__cta-color"
                        aria-label={`Fondo CTA #${position}`}
                        value={config.ctaColorModes[key] ?? "default"}
                        onChange={(event) => {
                          const mode = event.target.value as CtaColorMode;
                          setConfig((current) => {
                            if (!current) return current;
                            const next = { ...current.ctaColorModes };
                            if (mode === "default") delete next[key];
                            else next[key] = mode;
                            return { ...current, ctaColorModes: next };
                          });
                        }}
                      >
                        <option value="default">Predeterminado</option>
                        <option value="dark">Oscuro</option>
                        <option value="light">Claro</option>
                      </select>
                    </div>
                  );
                })}
              </div>
              {fieldErrors.cta_text_overrides && (
                <p
                  className="landings-field__error"
                  id="landing-cta-overrides-error"
                  role="alert"
                >
                  {fieldErrors.cta_text_overrides}
                </p>
              )}
              {fieldErrors.cta_color_modes && (
                <p className="landings-field__error" role="alert">
                  {fieldErrors.cta_color_modes}
                </p>
              )}
            </div>
          )}

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
                    ? {
                        ...current,
                        offerCount: count,
                        defaultOfferQuantity: Math.min(current.defaultOfferQuantity, count),
                        offers: fitOffers(current.offers, count),
                      }
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

          <div className="landings-field">
            <label className="landings-field__label" htmlFor="landing-default-offer">
              Oferta preseleccionada
            </label>
            <select
              id="landing-default-offer"
              className="landings-field__input"
              value={config.defaultOfferQuantity}
              aria-invalid={fieldErrors.default_offer_quantity ? true : undefined}
              onChange={(event) =>
                setConfig((current) =>
                  current
                    ? { ...current, defaultOfferQuantity: Number(event.target.value) }
                    : current,
                )
              }
            >
              {Array.from({ length: config.offerCount }, (_, index) => index + 1).map(
                (quantity) => (
                  <option key={quantity} value={quantity}>
                    {quantity === 1 ? "1 unidad" : `${quantity} unidades`}
                  </option>
                ),
              )}
            </select>
            <p className="landings-field__hint">
              Esta opción aparece elegida cuando se abre el formulario.
            </p>
            {fieldErrors.default_offer_quantity && (
              <p className="landings-field__error" role="alert">
                {fieldErrors.default_offer_quantity}
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
                  <div className="landings-offer__discounts">
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
                                    ? {
                                        ...item,
                                        discountPercent: event.target.value,
                                        discountAmount: event.target.value ? "" : item.discountAmount,
                                      }
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
                  <div className="landings-field">
                    <label
                      className="landings-field__label"
                      htmlFor={`landing-offer-discount-amount-${offer.quantity}`}
                    >
                      Descuento fijo (COP)
                    </label>
                    <input
                      id={`landing-offer-discount-amount-${offer.quantity}`}
                      className="landings-field__input"
                      type="number"
                      min={0}
                      step="0.01"
                      inputMode="decimal"
                      value={offer.discountAmount}
                      aria-describedby={`landing-offer-discount-amount-hint-${offer.quantity}`}
                      onChange={(event) =>
                        setConfig((current) =>
                          current
                            ? {
                                ...current,
                                offers: current.offers.map((item, itemIndex) =>
                                  itemIndex === index
                                    ? {
                                        ...item,
                                        discountAmount: event.target.value,
                                        discountPercent: event.target.value ? "" : item.discountPercent,
                                        calculatedDiscountPercent: 0,
                                      }
                                    : item,
                                ),
                              }
                            : current,
                        )
                      }
                    />
                    <p
                      className="landings-field__hint"
                      id={`landing-offer-discount-amount-hint-${offer.quantity}`}
                    >
                      {offer.discountAmount && offer.calculatedDiscountPercent > 0
                        ? `Equivale a ${offer.calculatedDiscountPercent}% y ese porcentaje se muestra al comprador.`
                        : "Valor exacto que se resta al total. Al guardarlo calculamos el porcentaje visible."}
                    </p>
                  </div>
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

        <SaveTemplateControl
          landingId={landing.id}
          bannerCount={banners.length}
          disabled={busy}
        />
      </section>

      <LandingBlocksPanel
        landingId={landing.id}
        sequenceSignature={`${banners.length}:${landing.resolved_cta_positions.join(",")}:${templateReloadToken}`}
        defaultAccentColor={
          config.blocksAccentColor || config.formAccentColor || config.accentColor
        }
        offerCount={config.offerCount}
      />
    </div>
  );
}
