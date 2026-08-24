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

import { Fragment, useEffect, useMemo, useState, type JSX } from "react";
import { useParams } from "react-router-dom";
import { Banner } from "../../components/Banner";
import { Cta } from "../../components/Cta";
import { Modal } from "../../components/Modal";
import { NotFoundPage } from "../../routes/NotFoundPage";
import { ApiError, publicApi } from "../../api";
import type {
  ConversionBlock,
  CtaBackground,
  CtaBandStyle,
  LocationCatalog,
  OrderCreateResponse,
  PublicLanding,
} from "../../api";
import { safeColor } from "../../utils";
import {
  trackInitiateCheckout,
  trackPurchase,
  type PurchaseCustomerData,
} from "../../analytics/metaCommerce";
import { CodForm } from "./CodForm";
import { ConversionBlockView } from "./ConversionBlocks";
import "./LandingPage.css";

const CURRENCY_FORMATTER = new Intl.NumberFormat("es-CO", {
  style: "currency",
  currency: "COP",
  maximumFractionDigits: 0,
});

type LoadState = "loading" | "ready" | "not-found" | "error";
type FormState = "closed" | "open";

const PRICE_FLOW_TYPES = ["price_summary", "store_trust", "purchase_benefits"] as const;

export function LandingPage(): JSX.Element {
  const { slug } = useParams<{ slug: string }>();
  const [landing, setLanding] = useState<PublicLanding | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [formState, setFormState] = useState<FormState>("closed");
  const [order, setOrder] = useState<OrderCreateResponse | null>(null);
  const [locations, setLocations] = useState<LocationCatalog | null>(null);

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

  useEffect(() => {
    let cancelled = false;
    void publicApi
      .getLocations()
      .then((catalog) => {
        if (!cancelled) setLocations(catalog);
      })
      .catch(() => {
        if (!cancelled) setLocations(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
    trackInitiateCheckout(landing);
    setFormState("open");
  }

  function handleOrderSuccess(
    result: OrderCreateResponse,
    purchase: PurchaseCustomerData & { quantity: number },
  ) {
    // Both pending and fraud-flagged submissions are durable COD orders. For
    // now, report both as purchases; fraud filtering can be added later if its
    // observed rate is high enough to justify excluding flagged traffic.
    if (landing) {
      trackPurchase(landing, {
        ...purchase,
        orderId: result.order_id,
        value: result.total_price,
      });
    }
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
  const visibleOffers = landing.offers ?? [];
  // Conversion components in render order. Absent on payloads cached before the
  // feature existed, and re-sorted defensively so a client never depends on the
  // server's ordering to place them correctly.
  const placedBlocks: ConversionBlock[] = [...(landing.blocks ?? [])].sort(
    (a, b) => a.slot_index - b.slot_index || a.order_index - b.order_index,
  );

  function priceFlowJoins(block: ConversionBlock): {
    joinPriceBefore: boolean;
    joinPriceAfter: boolean;
  } {
    const flowIndex = PRICE_FLOW_TYPES.indexOf(
      block.block_type as (typeof PRICE_FLOW_TYPES)[number],
    );
    if (flowIndex < 0) return { joinPriceBefore: false, joinPriceAfter: false };
    const index = placedBlocks.indexOf(block);
    const previous = placedBlocks[index - 1];
    const next = placedBlocks[index + 1];
    return {
      joinPriceBefore: Boolean(
        flowIndex > 0 &&
        previous?.slot_index === block.slot_index &&
        previous.block_type === PRICE_FLOW_TYPES[flowIndex - 1],
      ),
      joinPriceAfter: Boolean(
        flowIndex < PRICE_FLOW_TYPES.length - 1 &&
        next?.slot_index === block.slot_index &&
        next.block_type === PRICE_FLOW_TYPES[flowIndex + 1],
      ),
    };
  }
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
      source: resolved ? background?.source ?? "fallback" : "fallback",
      // An unpainted band is neither style; reporting the landing's setting
      // there would claim a fill that is not on the element.
      bandStyle: resolved ? bandStyle : "fallback",
    };
  }

  // Captured after the null guards above: the render helpers below are nested
  // functions, where TypeScript cannot keep the narrowing of `landing`.
  const productPrice = landing.product_price;
  const defaultCtaLabel = `Pedir ahora — ${CURRENCY_FORMATTER.format(productPrice)}`;
  const ctaLabel = landing.cta_text || defaultCtaLabel;
  const ctaAnimation = landing.cta_animation ?? null;
  const ctaTextOverrides = landing.cta_text_overrides;
  const ctaColorModes = landing.cta_color_modes;

  /**
   * The label for the CTA at `position` (1-based): that position's override
   * when the merchant set one (e.g. only the second CTA saying "Lo quiero
   * ahora"), else the landing's default label.
   */
  function ctaLabelForPosition(position: number): string {
    const override = ctaTextOverrides?.[String(position)];
    return override && override.trim() ? override : ctaLabel;
  }

  /** One CTA band, painted for `position` (1-based). */
  function renderCtaBand(position: number) {
    const band = getCtaBandProps(position);
    const colorMode = ctaColorModes?.[String(position)] ?? "default";
    return (
      <div
        className="lp-page__cta-band"
        style={band.style}
        data-cta-source={band.source}
        data-cta-band-style={band.bandStyle}
        data-cta-color-mode={colorMode}
      >
        <div className="lp-page__cta-slot">
          <Cta
            label={ctaLabelForPosition(position)}
            onClick={handleActivateCta}
            animation={ctaAnimation}
          />
        </div>
      </div>
    );
  }

  /**
   * The flat sequence the page renders: banner, then a CTA band where the
   * configuration puts one, and so on. Conversion components are placed
   * *between* these elements, so this list is also what their `slot_index`
   * counts (see backend app/domains/landings/blocks.py).
   */
  const elements: { key: string; node: JSX.Element }[] = [];
  sortedBanners.forEach((banner, index) => {
    const position = index + 1;
    elements.push({
      key: `banner-${banner.id}`,
      node: (
        <Banner
          id={banner.id}
          alt_text={banner.alt_text}
          order_index={banner.order_index}
          variants={banner.variants}
          lazy={index > 0}
        />
      ),
    });
    if (ctaPositionSet.has(position)) {
      elements.push({ key: `cta-${position}`, node: renderCtaBand(position) });
    }
  });
  if (showTrailingCta) {
    elements.push({
      key: "cta-trailing",
      node: renderCtaBand(sortedBanners.length),
    });
  }

  /** Placed components grouped by the slot they follow, in stored order. */
  const blocksBySlot = new Map<number, typeof placedBlocks>();
  for (const block of placedBlocks) {
    const slot = Math.max(0, block.slot_index);
    const group = blocksBySlot.get(slot);
    if (group) group.push(block);
    else blocksBySlot.set(slot, [block]);
  }

  // Read once, here, rather than inside `renderBlocks`: the guard above has
  // already narrowed `landing` away from null, and reading it in a closure
  // asks the compiler to re-prove that at every call site.
  const blocksDarkMode = landing.blocks_dark_mode;
  const blocksAccentPalette =
    landing.blocks_accent_palette ?? landing.form_accent_palette ?? null;

  function renderBlocks(slot: number) {
    const group = blocksBySlot.get(slot);
    if (!group) return null;
    return group.map((block) => {
      const joins = priceFlowJoins(block);
      return <ConversionBlockView
        key={block.id}
        block={block}
        productPrice={productPrice}
        offers={visibleOffers}
        ctaLabel={ctaLabel}
        ctaAnimation={ctaAnimation}
        onActivateCta={handleActivateCta}
        blocksDarkMode={blocksDarkMode}
        blocksAccentPalette={blocksAccentPalette}
        {...joins}
      />;
    });
  }

  // A component placed beyond the current sequence (the merchant shortened the
  // banner list after placing it) renders at the end rather than disappearing.
  const trailingBlocks = placedBlocks.filter((block) => block.slot_index > elements.length);

  /**
   * The merchant's accent, applied as CSS custom properties on the page root so
   * one stored color themes the CTA, the offer tiles, focus rings, and accent
   * text together (every rule already reads `--lp-action*`).
   *
   * Each value goes through `safeColor` even though the backend validated and
   * derived them: these are API-boundary strings landing directly in a `style`
   * attribute, and an unset property harmlessly falls back to the stylesheet's
   * default rather than injecting anything.
   */
  const palette = landing.accent_palette;
  const accentStyle: React.CSSProperties = {};
  const accentProperties = accentStyle as Record<string, string>;
  const accent = safeColor(palette?.accent ?? landing.accent_color);
  const accentDeep = safeColor(palette?.deep);
  const accentTint = safeColor(palette?.tint);
  const accentInk = safeColor(palette?.ink);
  if (accent) accentProperties["--lp-action"] = accent;
  if (accentDeep) accentProperties["--lp-action-deep"] = accentDeep;
  if (accentTint) accentProperties["--lp-action-tint"] = accentTint;
  if (accentInk) accentProperties["--lp-action-ink"] = accentInk;

  /**
   * The COD form's own accent (tier tiles, focus rings, submit button),
   * independent of the CTA/page accent above. Falls back to the CTA's palette
   * when the landing never set one, so payloads cached before this field
   * existed keep rendering identically. Written onto both `accentStyle` and
   * `formAccentStyle`; conversion blocks receive their independently resolved
   * palette through `ConversionBlockView`.
   */
  const formPalette = landing.form_accent_palette ?? palette;
  const formAccent = safeColor(formPalette?.accent ?? landing.form_accent_color ?? accent);
  const formAccentDeep = safeColor(formPalette?.deep);
  const formAccentTint = safeColor(formPalette?.tint);
  const formAccentInk = safeColor(formPalette?.ink);
  if (formAccent) accentProperties["--lp-form-action"] = formAccent;
  if (formAccentDeep) accentProperties["--lp-form-action-deep"] = formAccentDeep;
  if (formAccentTint) accentProperties["--lp-form-action-tint"] = formAccentTint;
  if (formAccentInk) accentProperties["--lp-form-action-ink"] = formAccentInk;

  // The modal needs both CTA and form variables since it's portaled outside
  // .lp-page. Spread accentStyle (which now includes both) into formAccentStyle.
  const formAccentStyle: React.CSSProperties = { ...accentStyle };

  return (
    <div className="lp-page" style={accentStyle}>
      <div className="lp-page__banners">
        {renderBlocks(0)}
        {elements.map((element, index) => (
          <Fragment key={element.key}>
            {element.node}
            {renderBlocks(index + 1)}
          </Fragment>
        ))}
        {trailingBlocks.map((block) => (
          <ConversionBlockView
            key={block.id}
            block={block}
            productPrice={productPrice}
            offers={visibleOffers}
            ctaLabel={ctaLabel}
            ctaAnimation={ctaAnimation}
            onActivateCta={handleActivateCta}
            blocksDarkMode={landing.blocks_dark_mode}
            blocksAccentPalette={blocksAccentPalette}
            {...priceFlowJoins(block)}
          />
        ))}
      </div>

      <Modal
        isOpen={formState === "open"}
        onClose={() => setFormState("closed")}
        title="Completa tu pedido - Envio GRATIS"
        subtitle="Paga cuando recibas"
        style={formAccentStyle}
      >
        <CodForm
          landingSlug={slug}
          productName={landing.product_name}
          unitPrice={landing.product_price}
          offers={landing.offers}
          defaultOfferQuantity={landing.default_offer_quantity}
          variantOptions={landing.variant_options}
          departments={locations?.departments ?? []}
          onSuccess={handleOrderSuccess}
        />
      </Modal>
    </div>
  );
}
