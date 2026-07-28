/**
 * Public product Landing (Requirements 3.21-3.26, 8.14-8.15). Renders the
 * banner sequence in stored order with CTAs at the configured positions,
 * opens the COD_Form as a pop-up dialog on CTA activation, and records one
 * view on successful display and one click per CTA activation. Mobile-first:
 * this is where cold ad traffic lands.
 *
 * The COD form is always Modal_Mode here: it is never rendered at the end of
 * the page. A buyer who taps a CTA next to banner 2 of 9 must not be sent to
 * the bottom of the page to find the fields — the sheet opens over the banner
 * they were looking at, keeps the offer recap in view, and closes back to the
 * same scroll position. `form_presentation` is still stored and editable in
 * the Admin Dashboard, but no longer changes what the public page renders
 * (Requirement 3.16 records the setting; 3.17-3.18 govern this dialog).
 *
 * Route: /p/:slug. Unknown/draft/paused/retired slugs return the same
 * 404 the backend returns (Requirement 3.24) — this page renders the
 * shared NotFoundPage rather than a distinct "unavailable" state, so no
 * information about *why* a slug is unavailable ever reaches the visitor.
 */

import { useEffect, useMemo, useState, type JSX } from "react";
import { useParams } from "react-router-dom";
import { Banner } from "../../components/Banner";
import { Cta } from "../../components/Cta";
import { Modal } from "../../components/Modal";
import { NotFoundPage } from "../../routes/NotFoundPage";
import { ApiError, publicApi } from "../../api";
import type {
  CtaBackground,
  CtaBandStyle,
  OrderCreateResponse,
  PublicLanding,
} from "../../api";
import { safeColor } from "../../utils";
import { CodForm } from "./CodForm";
import "./LandingPage.css";

const CURRENCY_FORMATTER = new Intl.NumberFormat("es-CO", {
  style: "currency",
  currency: "COP",
  maximumFractionDigits: 0,
});

type LoadState = "loading" | "ready" | "not-found" | "error";
type FormState = "closed" | "open";

export function LandingPage(): JSX.Element {
  const { slug } = useParams<{ slug: string }>();
  const [landing, setLanding] = useState<PublicLanding | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [formState, setFormState] = useState<FormState>("closed");
  const [order, setOrder] = useState<OrderCreateResponse | null>(null);

  useEffect(() => {
    if (!slug) return;
    let cancelled = false;

    setLoadState("loading");
    setLanding(null);
    setOrder(null);
    setFormState("closed");

    publicApi
      .getLanding(slug)
      .then((data) => {
        if (cancelled) return;
        setLanding(data);
        setLoadState("ready");
        void publicApi.recordView(slug);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setLoadState("not-found");
        } else {
          setLoadState("error");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [slug]);

  const ctaPositionSet = useMemo(
    () => new Set(landing?.cta_positions ?? []),
    [landing?.cta_positions],
  );

  /** Map from 1-based position to its background descriptor. */
  const ctaBackgroundMap = useMemo(() => {
    const map = new Map<number, CtaBackground>();
    if (!landing?.cta_backgrounds) return map;
    for (const bg of landing.cta_backgrounds) {
      // Only store the first entry per position (ignore duplicates gracefully)
      if (!map.has(bg.position)) {
        map.set(bg.position, bg);
      }
    }
    return map;
  }, [landing?.cta_backgrounds]);

  function handleActivateCta() {
    if (!slug || !landing) return;
    void publicApi.recordCtaClick(slug);
    setFormState("open");
  }

  function handleOrderSuccess(result: OrderCreateResponse) {
    setOrder(result);
    setFormState("closed");
  }

  if (loadState === "loading") {
    return (
      <div className="lp-page" aria-busy="true" aria-label="Cargando producto">
        <div className="lp-skeleton lp-skeleton--banner" />
        <div className="lp-page__cta-slot">
          <div className="lp-skeleton" style={{ height: 52, borderRadius: 10 }} />
        </div>
      </div>
    );
  }

  if (loadState === "not-found") {
    return <NotFoundPage />;
  }

  if (loadState === "error" || !landing || !slug) {
    return (
      <div className="lp-page">
        <div className="lp-page__state">
          <p className="lp-page__state-title">No pudimos cargar esta página</p>
          <p className="lp-page__state-text">
            Revisa tu conexión a internet e intenta de nuevo.
          </p>
          <button
            type="button"
            className="lp-page__retry"
            onClick={() => window.location.reload()}
          >
            Reintentar
          </button>
        </div>
      </div>
    );
  }

  if (order) {
    return (
      <div className="lp-page">
        <div className="lp-page__state">
          <p className="lp-page__state-title">¡Pedido recibido!</p>
          <p className="lp-page__state-text">
            Pagas en efectivo cuando el mensajero entregue tu pedido. Te contactaremos
            para confirmar la entrega.
          </p>
        </div>
      </div>
    );
  }

  const sortedBanners = [...landing.banners].sort((a, b) => a.order_index - b.order_index);
  // `cta_positions` is 1-based (see backend cta_placement.compute_cta_positions),
  // so a trailing CTA is needed only when the last banner's position is absent.
  const showTrailingCta = !ctaPositionSet.has(sortedBanners.length);

  // Payloads cached before the setting existed carry no value; anything
  // unrecognized is treated as the gradient the page has always rendered.
  const bandStyle: CtaBandStyle = landing?.cta_band_style === "solid" ? "solid" : "gradient";

  /**
   * Build CSS custom properties and data attributes for a CTA band.
   * `position` is 1-based, matching the backend contract.
   *
   * Both gradient endpoints are always set together, or neither is: a
   * half-resolved gradient would blend into `transparent` and expose the
   * neutral token through one half of the band.
   *
   * A `solid` landing sets both endpoints to the same color, which the single
   * gradient CSS rule already renders as a flat fill — so there is no separate
   * solid code path to keep in sync with the gradient one.
   */
  function getCtaBandProps(position: number) {
    const background = ctaBackgroundMap.get(position);
    const top = safeColor(background?.top_color);
    const bottom = safeColor(background?.bottom_color);
    const blend = safeColor(background?.blend_color);

    // blend_color is the solid-fill equivalent: the midpoint of the two edges
    // when the band spans both, and the one usable edge otherwise. It is also
    // what a `solid` landing paints across the whole band.
    let bandTop: string | undefined;
    let bandBottom: string | undefined;
    if (bandStyle === "solid" && (blend ?? top ?? bottom)) {
      bandTop = blend ?? top ?? bottom;
      bandBottom = bandTop;
    } else if (top && bottom) {
      bandTop = top;
      bandBottom = bottom;
    } else if (blend) {
      bandTop = blend;
      bandBottom = blend;
    } else if (top ?? bottom) {
      bandTop = top ?? bottom;
      bandBottom = bandTop;
    }

    const resolved = bandTop !== undefined && bandBottom !== undefined;
    const style: React.CSSProperties = {};
    if (resolved) {
      const properties = style as Record<string, string>;
      properties["--cta-band-top"] = bandTop as string;
      properties["--cta-band-bottom"] = bandBottom as string;
      if (blend) properties["--cta-band-blend"] = blend;
    }

    return {
      style,
      // Without a painted band the neutral treatment is the only readable one,
      // whatever `foreground` claims.
      foreground: resolved ? (background?.foreground ?? "fallback") : "fallback",
      source: resolved ? background?.source ?? "fallback" : "fallback",
      // An unpainted band is neither style; reporting the landing's setting
      // there would claim a fill that is not on the element.
      bandStyle: resolved ? bandStyle : "fallback",
    };
  }

  return (
    <div className="lp-page">
      <div className="lp-page__banners">
        {sortedBanners.map((banner, index) => {
          const position = index + 1;
          const band = ctaPositionSet.has(position) ? getCtaBandProps(position) : null;
          return (
            <div key={banner.id}>
              <Banner
                id={banner.id}
                alt_text={banner.alt_text}
                order_index={banner.order_index}
                variants={banner.variants}
                lazy={index > 0}
              />
              {band && (
                <div
                  className="lp-page__cta-band"
                  style={band.style}
                  data-cta-foreground={band.foreground}
                  data-cta-source={band.source}
                  data-cta-band-style={band.bandStyle}
                >
                  <div className="lp-page__cta-slot">
                    <Cta
                      label={`Pedir ahora — ${CURRENCY_FORMATTER.format(landing.product_price)}`}
                      onClick={handleActivateCta}
                    />
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {showTrailingCta && (() => {
        const band = getCtaBandProps(sortedBanners.length);
        return (
          <div
            className="lp-page__cta-band"
            style={band.style}
            data-cta-foreground={band.foreground}
            data-cta-source={band.source}
            data-cta-band-style={band.bandStyle}
          >
            <div className="lp-page__cta-slot">
              <Cta
                label={`Pedir ahora — ${CURRENCY_FORMATTER.format(landing.product_price)}`}
                onClick={handleActivateCta}
              />
            </div>
          </div>
        );
      })()}

      <Modal
        isOpen={formState === "open"}
        onClose={() => setFormState("closed")}
        title="Completa tu pedido"
        subtitle="Pago contraentrega: pagas al recibir."
      >
        <CodForm
          landingSlug={slug}
          productName={landing.product_name}
          unitPrice={landing.product_price}
          onSuccess={handleOrderSuccess}
        />
      </Modal>
    </div>
  );
}
