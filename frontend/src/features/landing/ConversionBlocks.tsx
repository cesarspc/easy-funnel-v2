/**
 * Fixed conversion components a landing can place between page elements or
 * above its first banner (Requirements 3.27-3.31).
 *
 * Every component's presentation lives here and nowhere else: the merchant
 * places a type in a slot and writes its content, and cannot change spacing,
 * type scale, or internal order. That is the point of a fixed
 * vocabulary — a component whose job is to convert should not be de-optimizable
 * from a settings screen. The one configurable presentation knob is
 * `accent_color`: every type accepts it, applied as a scoped CSS variable
 * override so that component's buttons/lines/background use it instead of the
 * landing's form accent — a single bounded field, not a door into arbitrary
 * styling.
 *
 * This pass restyles every component against reference screenshots of
 * high-converting cash-on-delivery landings. Where a component's config
 * shape had to grow to support the new layout, it grew in an
 * additive/optional way — older stored content (a bare `items: string[]`
 * for `benefits`, a bare `text` for `announcement_bar`) still renders,
 * just via the previous, simpler layout, so this is not a breaking change
 * for landings written before the redesign.
 *
 * What each one is for, against cold cash-on-delivery traffic on a phone:
 *
 * - `announcement_bar` — the first thing a visitor sees, above the hero
 *   banner. A `text`-only config renders the original one-line accent strip.
 *   An `items` config renders the new urgency card: a countdown-flavored
 *   title, icon bullet lines, and an optional stock bar — built to create
 *   movement ("order now"), not just announce a promo.
 * - `cod_assurance` — removes the payment objection at the moment it
 *   appears. Its three points are platform facts (pay on delivery, check
 *   first, no card), so they stay fixed copy; a merchant note and an
 *   optional delivery window are the configurable parts.
 * - `benefits` — "why this, not the generic thing": a two-column
 *   comparison table (`rows`) when the merchant has written one, or the
 *   original scannable checklist (`items`) otherwise.
 * - `offer_price` — preserves the original combined price/trust/logistics
 *   presentation for existing landings. New landings compose the identical
 *   visual from `price_summary`, `store_trust`, and `purchase_benefits`.
 * - `price_summary` — states price and, when the merchant declares a
 *   reference price, the saving — as a badge next to the number and a
 *   money-amount pill, the two most legible ways to say "you're saving"
 *   on a small screen. The selling price always comes from the product, so
 *   it cannot disagree with what the order charges.
 * - `spacer` — inserts one fixed vertical rhythm unit between components.
 * - `included_benefits` — what's included in the purchase, with optional value
 *   and tag per item, because showing the total value the buyer gets drives
 *   conversions for COD bundles.
 * - `reviews` — social proof with a name and city; the merchant supplies
 *   real ones, this renders them. Two visual variants, picked with
 *   `variant`: `"detailed"` (default) pairs a rating header and quality
 *   bars with pull-quote review cards; `"verified"` pairs an overall score
 *   with order-number / phone-tail / date proof lines per review.
 * - `faq` — native `<details>` accordion: answers objections without
 *   pushing the CTA off the screen.
 * - `guarantee` — risk reversal, stated once, plainly, or as a richer
 *   shield-and-benefits card when the merchant supplies benefit cards.
 * - The five story components turn the problem, solution, process, audience,
 *   and decision moment into a coherent long-form sales sequence.
 */

import { useEffect, useRef, useState, type CSSProperties, type JSX } from "react";
import type { AccentPalette, ConversionBlock, ConversionBlockConfig } from "../../api";
import { Cta } from "../../components/Cta";
import { safeColor } from "../../utils";
import "./ConversionBlocks.css";

const CURRENCY = new Intl.NumberFormat("es-CO", {
  style: "currency",
  currency: "COP",
  maximumFractionDigits: 0,
});

export interface ConversionBlockViewProps {
  block: ConversionBlock;
  /** Product price, used by `offer_price` so it can never disagree with the order. */
  productPrice: number;
  /** Landing-level dark mode default. Individual blocks override via config.dark_mode. */
  blocksDarkMode?: boolean;
  /** Landing-level block accent. A block's own palette overrides it. */
  blocksAccentPalette?: AccentPalette | null;
  /** Existing landing CTA behavior reused by an inserted CTA component. */
  ctaLabel: string;
  ctaAnimation?: "slide" | "shake" | null;
  onActivateCta: () => void;
  /** Collapse outer padding only when modular price parts are consecutive. */
  joinPriceBefore?: boolean;
  joinPriceAfter?: boolean;
}

/**
 * `ConversionBlockConfig` is a fixed shape per pre-existing block type. The
 * fields this redesign adds (`rows`, `variant`, `stats`, delivery-window
 * dates, etc.) are additive and merchant-optional, so rather than widen the
 * shared type for every block type they're read through this permissive
 * view and validated at runtime, the same way `asStrings`/`asReviews`/
 * `asFaqItems` already validate the pre-existing loosely-typed fields below.
 */
type LooseConfig = ConversionBlockConfig & Record<string, unknown>;

function asStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function asOptionalString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function asOptionalNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/**
 * Scoped accent override for one component, from its server-derived palette.
 * When a component has no override (`palette` is `null`) this returns
 * `undefined` rather than an empty object — no inline `style` prop is added,
 * and the component simply inherits `--lp-form-action*` from the page root
 * (Requirement: default accent = form accent).
 *
 * All four shades are overridden together so a merchant's color never leaves
 * a checkmark or step number painted in the *page's* accent next to text
 * colored in the *override* — the two would visibly disagree. `deep`/`tint`/
 * `ink` come pre-derived from the backend (same contrast-safe math as the
 * landing's own accent), so this never risks unreadable text.
 */
function accentStyle(palette: AccentPalette | null | undefined): CSSProperties | undefined {
  const accent = safeColor(palette?.accent);
  if (!accent) return undefined;
  const deep = safeColor(palette?.deep) ?? accent;
  const tint = safeColor(palette?.tint) ?? accent;
  const ink = safeColor(palette?.ink) ?? "#ffffff";
  const style: Record<string, string> = {
    "--lp-form-action": accent,
    "--lp-form-action-deep": deep,
    "--lp-form-action-tint": tint,
    "--lp-form-action-ink": ink,
  };
  return style as CSSProperties;
}

/** The shared CTA reads page-action tokens; mirror the component palette into
 * those tokens so a CTA block can use the same bounded accent override. */
function ctaAccentStyle(palette: AccentPalette | null | undefined): CSSProperties | undefined {
  const style = accentStyle(palette) as Record<string, string> | undefined;
  if (!style) return undefined;
  return {
    ...style,
    "--lp-action": style["--lp-form-action"],
    "--lp-action-deep": style["--lp-form-action-deep"],
    "--lp-action-ink": style["--lp-form-action-ink"],
  } as CSSProperties;
}

function PurchaseCta({
  config,
  palette,
  fallbackLabel,
  animation,
  onActivate,
}: {
  config: ConversionBlockConfig;
  palette: AccentPalette | null;
  fallbackLabel: string;
  animation?: "slide" | "shake" | null;
  onActivate: () => void;
}): JSX.Element {
  const label = asOptionalString((config as LooseConfig).text) ?? fallbackLabel;
  return (
    <section className="cblock cblock--purchase-cta" style={ctaAccentStyle(palette)}>
      <Cta label={label} animation={animation} onClick={onActivate} />
    </section>
  );
}

function VideoCarousel({
  block,
  palette,
}: {
  block: ConversionBlock;
  palette: AccentPalette | null;
}): JSX.Element | null {
  const videos = block.videos;
  const [requestedIndex, setRequestedIndex] = useState(0);
  const [activatedVideoId, setActivatedVideoId] = useState<number | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  // Posters are tiny immutable WebPs. Preloading at most six of them makes
  // arrow navigation immediate without preloading a single inactive MP4.
  useEffect(() => {
    const posters = (videos ?? []).map((video) => {
      const image = new Image();
      image.src = video.poster_url;
      return image;
    });
    return () => posters.forEach((image) => image.removeAttribute("src"));
  }, [videos]);

  const safeVideos = videos ?? [];
  const videoCount = safeVideos.length;
  const activeIndex = videoCount > 0 ? Math.min(requestedIndex, videoCount - 1) : 0;
  const active = safeVideos[activeIndex];
  const multiple = videoCount > 1;
  const isActivated = active ? activatedVideoId === active.id : false;

  if (!active) return null;

  function move(delta: number) {
    setActivatedVideoId(null);
    setIsPlaying(false);
    setIsLoading(false);
    setRequestedIndex((current) => (current + delta + videoCount) % videoCount);
  }

  function select(index: number) {
    setActivatedVideoId(null);
    setIsPlaying(false);
    setIsLoading(false);
    setRequestedIndex(index);
  }

  function togglePlayback() {
    const player = videoRef.current;
    if (!player) return;
    if (isPlaying) {
      player.pause();
      setIsPlaying(false);
      return;
    }
    setActivatedVideoId(active.id);
    // A second tap must never be ignored while a mobile browser is preparing
    // playback. Calling play again is harmless and lets the browser retry
    // without making the visitor wait for a spinner that appears stuck.
    setIsLoading(player.readyState < HTMLMediaElement.HAVE_FUTURE_DATA);
    const playback = player.play();
    void playback.catch(() => {
      setActivatedVideoId(null);
      setIsLoading(false);
      setIsPlaying(false);
    });
  }

  return (
    <section
      className="cblock cblock--video-carousel"
      style={accentStyle(palette)}
      aria-roledescription="carrusel"
      aria-label={asOptionalString(block.config.title) ?? "Videos del producto"}
    >
      <BlockHeading title={block.config.title} />
      <div className="cblock__video-stage">
        <video
          ref={videoRef}
          key={`player-${active.id}`}
          className="cblock__video"
          src={active.url}
          playsInline
          preload="auto"
          poster={active.poster_url}
          width={active.width}
          height={active.height}
          aria-label={active.caption ?? `Video ${activeIndex + 1}`}
          onPlaying={() => {
            setIsLoading(false);
            setIsPlaying(true);
          }}
          onWaiting={() => {
            if (isActivated) setIsLoading(true);
          }}
          onPause={() => setIsPlaying(false)}
          onEnded={() => {
            setIsLoading(false);
            setIsPlaying(false);
          }}
        />
        {!isActivated && (
          <img
            key={`poster-${active.id}`}
            className="cblock__video-poster"
            src={active.poster_url}
            alt=""
            width={active.width}
            height={active.height}
            decoding="async"
          />
        )}
        <button
          type="button"
          className={`cblock__video-play${isLoading ? " is-loading" : ""}`}
          aria-label={`${isLoading ? "Cargando" : isPlaying ? "Pausar" : "Reproducir"} ${active.caption ?? `video ${activeIndex + 1}`}`}
          aria-busy={isLoading}
          onClick={togglePlayback}
        >
          {isLoading ? (
            <span className="cblock__video-spinner" aria-hidden="true" />
          ) : isPlaying ? (
            <svg className="cblock__video-pause-icon" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M7 5h4v14H7zM13 5h4v14h-4z" />
            </svg>
          ) : (
            <svg className="cblock__video-play-icon" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M8 5v14l11-7z" />
            </svg>
          )}
        </button>
      </div>
      {multiple && (
        <div className="cblock__video-navigation">
          <div className="cblock__video-arrows">
            <button type="button" aria-label="Video anterior" onClick={() => move(-1)}>‹</button>
            <button type="button" aria-label="Video siguiente" onClick={() => move(1)}>›</button>
          </div>
          <div className="cblock__video-tabs" aria-label="Seleccionar video">
            {safeVideos.map((video, index) => (
              <button
                type="button"
                key={video.id}
                className={index === activeIndex ? "is-active" : undefined}
                aria-label={`Ir al video ${index + 1}`}
                aria-current={index === activeIndex ? "true" : undefined}
                onClick={() => select(index)}
              >
                {index + 1}
              </button>
            ))}
          </div>
        </div>
      )}
      {active.caption && <p className="cblock__video-caption" aria-live="polite">{active.caption}</p>}
    </section>
  );
}

/** Deterministic avatar palette so the same reviewer name always draws the same color. */
const AVATAR_COLORS = ["#f97316", "#0ea5e9", "#22c55e", "#a855f7", "#ef4444", "#14b8a6", "#eab308"];

function avatarColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i += 1) hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  return AVATAR_COLORS[hash % AVATAR_COLORS.length];
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const chars = parts.slice(0, 2).map((part) => part[0]?.toUpperCase() ?? "");
  return chars.join("") || "?";
}

interface ReviewItem {
  name: string;
  city?: string | null;
  text: string;
  rating?: number | null;
  /** Bold pull-line shown above the quote in the "detailed" variant. */
  headline?: string | null;
  /** Reviews shown here are always from real buyers; defaults true. */
  verified: boolean;
  /** e.g. "Instagram" / "Compra web" — used by the "verified" variant. */
  channel?: string | null;
  order_id?: string | null;
  phone?: string | null;
  date?: string | null;
}

function asReviews(value: unknown): ReviewItem[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (typeof item !== "object" || item === null) return [];
    const candidate = item as Record<string, unknown>;
    if (typeof candidate.name !== "string" || typeof candidate.text !== "string") return [];
    return [
      {
        name: candidate.name,
        city: typeof candidate.city === "string" ? candidate.city : null,
        text: candidate.text,
        rating: typeof candidate.rating === "number" ? candidate.rating : null,
        headline: typeof candidate.headline === "string" ? candidate.headline : null,
        verified: typeof candidate.verified === "boolean" ? candidate.verified : true,
        channel: typeof candidate.channel === "string" ? candidate.channel : null,
        order_id: typeof candidate.order_id === "string" ? candidate.order_id : null,
        phone: typeof candidate.phone === "string" ? candidate.phone : null,
        date: typeof candidate.date === "string" ? candidate.date : null,
      },
    ];
  });
}

interface QualityMetric {
  label: string;
  percent: number;
}

function asQualityMetrics(value: unknown): QualityMetric[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (typeof item !== "object" || item === null) return [];
    const candidate = item as Record<string, unknown>;
    if (typeof candidate.label !== "string" || typeof candidate.percent !== "number") return [];
    return [{ label: candidate.label, percent: Math.min(100, Math.max(0, candidate.percent)) }];
  });
}

interface FaqItem {
  question: string;
  answer: string;
}

function asFaqItems(value: unknown): FaqItem[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (typeof item !== "object" || item === null) return [];
    const candidate = item as Record<string, unknown>;
    if (typeof candidate.question !== "string" || typeof candidate.answer !== "string") return [];
    return [{ question: candidate.question, answer: candidate.answer }];
  });
}

interface CompareRow {
  label: string;
  common: string;
  ours: string;
}

function asCompareRows(value: unknown): CompareRow[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (typeof item !== "object" || item === null) return [];
    const candidate = item as Record<string, unknown>;
    if (
      typeof candidate.label !== "string" ||
      typeof candidate.common !== "string" ||
      typeof candidate.ours !== "string"
    ) {
      return [];
    }
    return [{ label: candidate.label, common: candidate.common, ours: candidate.ours }];
  });
}

interface UrgencyItem {
  /** Bold lead phrase, e.g. "Pedidos antes de las 2:00 p.m." */
  lead: string;
  /** Plain continuation, e.g. "salen el mismo día" */
  text?: string | null;
}

function asUrgencyItems(value: unknown): UrgencyItem[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (typeof item !== "object" || item === null) return [];
    const candidate = item as Record<string, unknown>;
    if (typeof candidate.lead !== "string") return [];
    return [{ lead: candidate.lead, text: typeof candidate.text === "string" ? candidate.text : null }];
  });
}

interface TrustStat {
  /** Optional lead number, e.g. "37.320" — omit for an icon-style stat with only a label. */
  value?: string | null;
  label: string;
}

interface StoryCard {
  title: string;
  text: string | null;
  kicker: string | null;
}

function asStoryCards(value: unknown): StoryCard[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (typeof item !== "object" || item === null) return [];
    const candidate = item as Record<string, unknown>;
    if (typeof candidate.title !== "string") return [];
    return [{
      title: candidate.title,
      text: typeof candidate.text === "string" ? candidate.text : null,
      kicker: typeof candidate.kicker === "string" ? candidate.kicker : null,
    }];
  });
}

function asTrustStats(value: unknown): TrustStat[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (typeof item !== "object" || item === null) return [];
    const candidate = item as Record<string, unknown>;
    if (typeof candidate.label !== "string") return [];
    return [{ value: typeof candidate.value === "string" ? candidate.value : null, label: candidate.label }];
  });
}

function BlockHeading({ title }: { title?: string | null }): JSX.Element | null {
  if (!title) return null;
  return <h2 className="cblock__title">{title}</h2>;
}

function StoryTitle({ title, highlight }: { title: string; highlight?: string | null }): JSX.Element {
  return (
    <h2 className="cblock__story-title">
      <span>{title}</span>
      {highlight && <strong>{highlight}</strong>}
    </h2>
  );
}

const URGENCY_ICONS = ["⏰", "📦", "🚚", "🔥", "🎁"];

/**
 * Top-of-page announcement. Renders the rich urgency card (reference:
 * "Aprovecha hoy") whenever the merchant has written `items`; falls back to
 * the original one-line accent strip for a bare `text` config, so landings
 * saved before this redesign keep rendering unchanged.
 */
function AnnouncementBar({
  config,
  palette,
}: {
  config: ConversionBlockConfig;
  palette: AccentPalette | null;
}): JSX.Element | null {
  const loose = config as LooseConfig;
  const items = asUrgencyItems(loose.items);

  if (items.length > 0) {
    const title = asOptionalString(config.title) ?? "Aprovecha hoy";
    const stockLabel = asOptionalString(loose.stock_label);
    const stockPercentRaw = asOptionalNumber(loose.stock_percent);
    const stockPercent = stockPercentRaw === null ? null : Math.min(100, Math.max(0, stockPercentRaw));

    return (
      <section className="cblock cblock--urgency" style={accentStyle(palette)} role="note" aria-label={title}>
        <p className="cblock__urgency-title">
          <span aria-hidden="true">⏰</span> {title}
        </p>
        <ul className="cblock__urgency-list">
          {items.map((item, index) => (
            <li key={`${item.lead}-${index}`}>
              <span className="cblock__urgency-icon" aria-hidden="true">
                {URGENCY_ICONS[index % URGENCY_ICONS.length]}
              </span>
              <span>
                <strong>{item.lead}</strong>
                {item.text ? ` ${item.text}` : ""}
              </span>
            </li>
          ))}
        </ul>
        {stockLabel && (
          <div className="cblock__urgency-stock">
            <p className="cblock__urgency-stock-label">{stockLabel}</p>
            {stockPercent !== null && (
              <div
                className="cblock__urgency-bar"
                role="progressbar"
                aria-valuenow={stockPercent}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={stockLabel}
              >
                <div className="cblock__urgency-bar-fill" style={{ width: `${stockPercent}%` }} />
              </div>
            )}
          </div>
        )}
      </section>
    );
  }

  if (!config.text) return null;
  return (
    <section className="cblock cblock--announcement" style={accentStyle(palette)} role="note">
      <p className="cblock__announcement-text">{config.text}</p>
    </section>
  );
}

/** Pay-on-delivery assurances. Fixed copy: these are facts about the platform. */
function CodAssurance({
  config,
  palette,
}: {
  config: ConversionBlockConfig;
  palette: AccentPalette | null;
}): JSX.Element {
  const loose = config as LooseConfig;
  const deliveryFrom = asOptionalString(loose.delivery_from);
  const deliveryTo = asOptionalString(loose.delivery_to);

  return (
    <section
      className="cblock cblock--assurance"
      style={accentStyle(palette)}
      aria-label="Pago contraentrega"
    >
      <ul className="cblock__assurances">
        <li>
          <span className="cblock__assurances-icon" aria-hidden="true">
            $
          </span>
          <p className="cblock__assurances-line">
            <strong>Pagas al recibir</strong>
            <span className="cblock__assurances-detail">En efectivo, cuando el pedido llega a tu puerta.</span>
          </p>
        </li>
        <li>
          <span className="cblock__assurances-icon" aria-hidden="true">
            ◎
          </span>
          <p className="cblock__assurances-line">
            <strong>Revisas antes de pagar</strong>
            <span className="cblock__assurances-detail">Ves el producto con el mensajero presente.</span>
          </p>
        </li>
        <li>
          <span className="cblock__assurances-icon" aria-hidden="true">
            ⛔
          </span>
          <p className="cblock__assurances-line">
            <strong>Sin tarjeta</strong>
            <span className="cblock__assurances-detail">No pedimos datos bancarios en ningún momento.</span>
          </p>
        </li>
      </ul>
      {deliveryFrom && deliveryTo && (
        <p className="cblock__assurances-delivery">
          Se entrega entre el: {deliveryFrom} al {deliveryTo}.
        </p>
      )}
      {config.note && <p className="cblock__note">{config.note}</p>}
    </section>
  );
}

/**
 * "Why this, not the generic thing." Renders a head-to-head comparison
 * table when the merchant has written `rows`; falls back to the original
 * checklist for a bare `items: string[]` config.
 */
function Benefits({
  config,
  palette,
}: {
  config: ConversionBlockConfig;
  palette: AccentPalette | null;
}): JSX.Element | null {
  const loose = config as LooseConfig;
  const rows = asCompareRows(loose.rows);
  const legacyItems = asStrings(config.items);
  if (rows.length === 0 && legacyItems.length === 0) return null;

  const oursLabel = asOptionalString(loose.ours_label) ?? "Este producto";

  return (
    <section className="cblock cblock--benefits" style={accentStyle(palette)}>
      <BlockHeading title={config.title ?? "Por qué elegir este producto"} />
      {rows.length > 0 ? (
        <div className="cblock__compare" role="table" aria-label="Comparación de producto">
          <div className="cblock__compare-row cblock__compare-row--head" role="row">
            <span className="cblock__compare-cell cblock__compare-cell--label" role="columnheader" aria-hidden="true" />
            <span className="cblock__compare-cell cblock__compare-cell--common" role="columnheader">
              Común
            </span>
            <span className="cblock__compare-cell cblock__compare-cell--ours" role="columnheader">
              {oursLabel}
            </span>
          </div>
          {rows.map((row) => (
            <div className="cblock__compare-row" role="row" key={row.label}>
              <span className="cblock__compare-cell cblock__compare-cell--label" role="rowheader">
                {row.label}
              </span>
              <span className="cblock__compare-cell cblock__compare-cell--common" role="cell">
                <span className="cblock__compare-icon--no" aria-hidden="true">
                  ✕
                </span>
                {row.common}
              </span>
              <span className="cblock__compare-cell cblock__compare-cell--ours" role="cell">
                <span className="cblock__compare-icon--yes" aria-hidden="true">
                  ✓
                </span>
                {row.ours}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <ul className="cblock__benefits">
          {legacyItems.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

function OfferPrice({
  config,
  productPrice,
  palette,
  mode = "combined",
  joinBefore = false,
  joinAfter = false,
}: {
  config: ConversionBlockConfig;
  productPrice: number;
  palette: AccentPalette | null;
  mode?: "combined" | "price" | "trust" | "benefits";
  joinBefore?: boolean;
  joinAfter?: boolean;
}): JSX.Element {
  const loose = config as LooseConfig;
  const compareAt =
    typeof config.compare_at_price === "number" && config.compare_at_price > productPrice
      ? config.compare_at_price
      : null;
  const savings = compareAt === null ? null : compareAt - productPrice;
  const percent =
    compareAt === null || savings === null ? null : Math.round((savings / compareAt) * 100);

  // Trust badge fields
  const trustStats = asTrustStats(loose.stats);

  // Shipping/guarantee info card fields
  const shippingLabel = asOptionalString(loose.shipping_label) ?? "Envío Gratis";
  const shippingTag = asOptionalString(loose.shipping_tag); // e.g. "FULL"
  const shippingAvailable = asOptionalString(loose.shipping_available) ?? "Disponible";
  const deliveryFrom = asOptionalString(loose.delivery_from);
  const deliveryTo = asOptionalString(loose.delivery_to);
  const bestseller = asOptionalString(loose.bestseller_label);

  const modularClass = mode === "combined"
    ? "cblock cblock--price"
    : [
        "cblock",
        "cblock--price-module",
        `cblock--price-${mode}`,
        joinBefore ? "cblock--price-joined-before" : "",
        joinAfter ? "cblock--price-joined-after" : "",
      ].filter(Boolean).join(" ");

  return (
    <section className={modularClass} style={accentStyle(palette)} aria-label={
      mode === "price" ? "Precio" : mode === "trust" ? "Tienda certificada" :
      mode === "benefits" ? "Envío, pago y garantía" : "Precio"
    }>
      {/* ──── Part 1: Price card ──── */}
      {(mode === "combined" || mode === "price") && <div className="cblock__price-card">
        <p className="cblock__price-eyebrow">{config.title || "Precio:"}</p>
        {compareAt !== null && (
          <p className="cblock__price-was">
            <span className="sr-only">Antes </span>
            DE {CURRENCY.format(compareAt)}
          </p>
        )}

        <div className="cblock__price-now-row">
          <p className="cblock__price-now" aria-label={`Precio: ${CURRENCY.format(productPrice)}`}>
            {CURRENCY.format(productPrice)}
          </p>
          {percent !== null && (
            <span className="cblock__price-badge" aria-label={`${percent}% de descuento`}>
              <svg className="cblock__price-badge-icon" viewBox="0 0 12 12" fill="currentColor" aria-hidden="true">
                <path d="M6 1l1.5 3.5L11 5l-2.5 2.5.5 3.5L6 9.5 3 11l.5-3.5L1 5l3.5-.5z" />
              </svg>
              {percent}%
            </span>
          )}
        </div>

        {savings !== null && (
          <p className="cblock__price-discount-pill">
            {CURRENCY.format(savings)} de descuento
          </p>
        )}
      </div>}

      {/* ──── Part 2: Trust badge ──── */}
      {(mode === "combined" || mode === "trust") && <div className="cblock__trust-badge">
        <div className="cblock__trust-topbar" aria-hidden="true" />

        <div className="cblock__trust-header">
          <svg className="cblock__trust-shield" viewBox="0 0 40 40" fill="none" aria-hidden="true">
            <circle cx="20" cy="20" r="18" fill="#e8f5e9" />
            <path d="M20 8l8 4v6c0 5.5-3.5 10.5-8 12-4.5-1.5-8-6.5-8-12v-6l8-4z" fill="#4caf50" />
            <path d="M17 20l2.5 2.5L24 17" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none" />
          </svg>
          <div className="cblock__trust-titles">
            <p className="cblock__trust-title">Tienda Lider Certificada</p>
            <p className="cblock__trust-subtitle">Líderes en Comercio <strong>bodegapremium.co</strong></p>
          </div>
        </div>

        <div className="cblock__trust-meter" aria-hidden="true">
          <div className="cblock__trust-meter-fill" />
          <div className="cblock__trust-meter-indicator" />
        </div>

        {trustStats.length > 0 && (
          <div className="cblock__trust-stats">
            {trustStats.map((stat, index) => (
              <div key={stat.label} className="cblock__trust-stat">
                {index > 0 && <div className="cblock__trust-stat-divider" aria-hidden="true" />}
                {stat.value && <p className="cblock__trust-stat-value">{stat.value}</p>}
                <p className="cblock__trust-stat-label">{stat.label}</p>
              </div>
            ))}
          </div>
        )}
      </div>}

      {/* ──── Part 3: Shipping, COD & guarantee info card ──── */}
      {(mode === "combined" || mode === "benefits") && <div className="cblock__price-info">
        <div className="cblock__info-row cblock__info-row--shipping">
          <svg className="cblock__info-icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path d="M8 16.5a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0zM15 16.5a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0zM3 4h2l.4 2M7 13h6l4-8H5.4M7 13L5.4 6M7 13l-1.7 2" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          <p className="cblock__info-text">
            <strong>{shippingLabel}</strong>
            {shippingTag && <span className="cblock__info-tag">{shippingTag}</span>}
            <span className="cblock__info-dot">·</span>
            <span>{shippingAvailable}</span>
          </p>
        </div>

        <div className="cblock__info-row">
          <svg className="cblock__info-icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path fillRule="evenodd" d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z" clipRule="evenodd"/>
          </svg>
          <p className="cblock__info-text">
            Pago Contraentrega Seguro de Envío
            {deliveryFrom && deliveryTo && (
              <>
                <br />
                <span className="cblock__info-delivery">
                  Se entrega entre el: {deliveryFrom} al {deliveryTo}.
                </span>
              </>
            )}
          </p>
        </div>

        <div className="cblock__info-row">
          <svg className="cblock__info-icon cblock__info-icon--success" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
          </svg>
          <p className="cblock__info-text">Compra Garantizada: Si no es lo que esperas te devolvemos el 100%</p>
        </div>

        {bestseller && (
          <div className="cblock__info-row">
            <svg className="cblock__info-icon cblock__info-icon--highlight" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path d="M10 2a1 1 0 01.894.553l1.789 3.575 3.96.576a1 1 0 01.553 1.706l-2.867 2.794.677 3.943a1 1 0 01-1.451 1.054L10 14.347l-3.555 1.854A1 1 0 015 15.147l.677-3.943L2.804 8.41a1 1 0 01.553-1.706l3.96-.576L9.106 2.553A1 1 0 0110 2z" />
            </svg>
            <p className="cblock__info-text">
              <strong>Más Vendido</strong> {bestseller}
            </p>
          </div>
        )}

        {config.note && <p className="cblock__price-note">{config.note}</p>}
      </div>}
    </section>
  );
}

function Spacer(): JSX.Element {
  return <div className="cblock cblock--spacer" aria-hidden="true" />;
}

interface BenefitItem {
  name: string;
  value: string | null;
  tag: string | null;
}

function asBenefitItems(value: unknown): BenefitItem[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (typeof item !== "object" || item === null) return [];
    const candidate = item as Record<string, unknown>;
    if (typeof candidate.name !== "string" || !candidate.name.trim()) return [];
    return [
      {
        name: candidate.name,
        value: typeof candidate.value === "string" && candidate.value.trim() ? candidate.value : null,
        tag: typeof candidate.tag === "string" && candidate.tag.trim() ? candidate.tag : null,
      },
    ];
  });
}

function IncludedBenefits({
  config,
  palette,
}: {
  config: ConversionBlockConfig;
  palette: AccentPalette | null;
}): JSX.Element | null {
  const loose = config as LooseConfig;
  const items = asBenefitItems(loose.items);
  if (items.length === 0) return null;

  // Parse **bold** segments in the title for the "Todo lo que incluye **PRODUCT**" pattern
  const rawTitle = config.title ?? "Incluido en tu compra";
  const titleParts = rawTitle.split(/\*\*(.+?)\*\*/g);

  return (
    <section className="cblock cblock--included-benefits" style={accentStyle(palette)}>
      {/* Header with accent top rule */}
      <div className="cblock__benefits-header">
        <div className="cblock__benefits-header-rule" aria-hidden="true" />
        <h2 className="cblock__benefits-heading">
          {titleParts.map((part, i) =>
            i % 2 === 1 ? <strong key={i}>{part}</strong> : part
          )}
        </h2>
      </div>
      {/* Dark card body for the list */}
      <div className="cblock__benefits-card">
        <ul className="cblock__benefits-list">
          {items.map((item) => (
            <li key={item.name} className="cblock__benefit-row">
              <svg
                className="cblock__benefit-check"
                viewBox="0 0 20 20"
                fill="none"
                aria-hidden="true"
              >
                <circle cx="10" cy="10" r="10" fill="var(--lp-action)" />
                <path
                  d="M6 10.5l2.5 2.5L14 8"
                  stroke="#fff"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <span className="cblock__benefit-name">{item.name}</span>
              <span className="cblock__benefit-meta">
                {item.value && <span className="cblock__benefit-value">{item.value}</span>}
                {item.tag && <span className="cblock__benefit-tag">{item.tag}</span>}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

/** "Verified"-variant review card: order/phone/date proof instead of quality bars. */
function VerifiedReviewCard({ review }: { review: ReviewItem }): JSX.Element {
  const meta = [review.order_id ? `Pedido #${review.order_id}` : null, review.phone, review.date]
    .filter((part): part is string => Boolean(part))
    .join(" · ");

  return (
    <li className="cblock__review cblock__review--verified">
      <div className="cblock__review-head">
        <span className="cblock__review-avatar" aria-hidden="true" style={{ background: avatarColor(review.name) }}>
          {initials(review.name)}
        </span>
        <div className="cblock__review-identity">
          <p className="cblock__review-name">
            {review.name}
            {review.verified && (
              <span className="cblock__review-check" aria-label="Compra verificada">
                {" "}✓
              </span>
            )}
          </p>
          {review.city && (
            <p className="cblock__review-location">
              <span aria-hidden="true">📍</span> {review.city}
            </p>
          )}
          <p className="cblock__review-tag">
            Compra verificada
            {review.channel ? ` · ${review.channel}` : ""}
          </p>
        </div>
        {typeof review.rating === "number" && (
          <span className="cblock__review-score" aria-label={`${review.rating} de 5 estrellas`}>
            {review.rating.toFixed(1).replace(".", ",")}
          </span>
        )}
      </div>
      <p className="cblock__review-text">{review.text}</p>
      {meta && <p className="cblock__review-meta">{meta}</p>}
    </li>
  );
}

/** "Detailed"-variant review card: star rating, optional bold pull-line, then the quote. */
function DetailedReviewCard({ review }: { review: ReviewItem }): JSX.Element {
  return (
    <li className="cblock__review">
      <div className="cblock__review-head">
        <span className="cblock__review-avatar" aria-hidden="true" style={{ background: avatarColor(review.name) }}>
          {initials(review.name)}
        </span>
        {typeof review.rating === "number" && (
          <p className="cblock__rating" aria-label={`${review.rating} de 5 estrellas`}>
            <span aria-hidden="true">{"★".repeat(review.rating)}</span>
            <span aria-hidden="true" className="cblock__rating-empty">
              {"★".repeat(Math.max(0, 5 - review.rating))}
            </span>
          </p>
        )}
      </div>
      {review.headline && <p className="cblock__review-headline">{review.headline}</p>}
      <blockquote className="cblock__review-text">{review.text}</blockquote>
      <p className="cblock__review-author">
        {review.name}
        {review.city ? ` · ${review.city}` : ""}
      </p>
    </li>
  );
}

function Reviews({
  config,
  palette,
}: {
  config: ConversionBlockConfig;
  palette: AccentPalette | null;
}): JSX.Element | null {
  const loose = config as LooseConfig;
  const items = asReviews(loose.items);
  if (items.length === 0) return null;

  const variant = loose.variant === "verified" ? "verified" : "detailed";
  const rating = asOptionalNumber(loose.rating);
  const ratingCount = asOptionalNumber(loose.rating_count);

  if (variant === "verified") {
    return (
      <section className="cblock cblock--reviews cblock--reviews-verified" style={accentStyle(palette)}>
        <BlockHeading title={config.title ?? "Lo que dicen quienes ya lo recibieron"} />
        {rating !== null && (
          <p className="cblock__reviews-summary">
            <span aria-hidden="true">★</span>
            <strong>{rating.toFixed(1).replace(".", ",")}</strong>
            {ratingCount !== null && <span>· {ratingCount} opiniones reales de clientes</span>}
          </p>
        )}
        <ul className="cblock__reviews">
          {items.map((review) => (
            <VerifiedReviewCard key={`${review.name}-${review.text}`} review={review} />
          ))}
        </ul>
      </section>
    );
  }

  const metrics = asQualityMetrics(loose.quality_metrics);

  return (
    <section className="cblock cblock--reviews" style={accentStyle(palette)}>
      <BlockHeading title={config.title ?? "Reseñas"} />
      {rating !== null && (
        <p className="cblock__reviews-summary">
          <strong>{rating.toFixed(1).replace(".", ",")}</strong>
          <span aria-hidden="true">★★★★★</span>
          {ratingCount !== null && <span>{ratingCount} calificaciones</span>}
        </p>
      )}
      <p className="cblock__reviews-verified-line">✓ Todo desde compras verificadas</p>
      {metrics.length > 0 && (
        <ul className="cblock__reviews-metrics">
          {metrics.map((metric) => (
            <li key={metric.label}>
              <span className="cblock__reviews-metric-label">{metric.label}</span>
              <span className="cblock__reviews-metric-bar" aria-hidden="true">
                <span style={{ width: `${metric.percent}%` }} />
              </span>
              <span className="cblock__reviews-metric-value">{metric.percent}%</span>
            </li>
          ))}
        </ul>
      )}
      <ul className="cblock__reviews">
        {items.map((review) => (
          <DetailedReviewCard key={`${review.name}-${review.text}`} review={review} />
        ))}
      </ul>
    </section>
  );
}

function Faq({
  config,
  palette,
}: {
  config: ConversionBlockConfig;
  palette: AccentPalette | null;
}): JSX.Element | null {
  const items = asFaqItems(config.items);
  if (items.length === 0) return null;
  return (
    <section className="cblock cblock--faq" style={accentStyle(palette)}>
      <BlockHeading title={config.title ?? "Preguntas frecuentes"} />
      <div className="cblock__faq">
        {items.map((item) => (
          // Native <details>: keyboard-operable and screen-reader-announced
          // without any JavaScript, and collapsed by default so the answers
          // never push the CTA out of the viewport.
          <details key={item.question} className="cblock__faq-item">
            <summary className="cblock__faq-question">{item.question}</summary>
            <p className="cblock__faq-answer">{item.answer}</p>
          </details>
        ))}
      </div>
    </section>
  );
}

const STORY_ICONS = ["◷", "◎", "$", "◆", "↗", "✓"];

function MainProblem({ config, palette }: { config: ConversionBlockConfig; palette: AccentPalette | null }): JSX.Element | null {
  const loose = config as LooseConfig;
  const title = asOptionalString(loose.title);
  const items = asStoryCards(loose.items);
  if (!title || items.length === 0) return null;
  return (
    <section className="cblock cblock--story cblock--problem" style={accentStyle(palette)}>
      <div className="cblock__story-head">
        {asOptionalString(loose.eyebrow) && <p className="cblock__story-eyebrow">△ {String(loose.eyebrow)}</p>}
        <StoryTitle title={title} highlight={asOptionalString(loose.highlight)} />
        {asOptionalString(loose.subtitle) && <p className="cblock__story-subtitle">{String(loose.subtitle)}</p>}
      </div>
      <ul className="cblock__story-grid cblock__problem-grid">
        {items.map((item, index) => (
          <li className="cblock__story-card" key={`${item.title}-${index}`}>
            <span className="cblock__story-icon" aria-hidden="true">{STORY_ICONS[index % STORY_ICONS.length]}</span>
            <h3>{item.title}</h3>
            {item.text && <p>{item.text}</p>}
          </li>
        ))}
      </ul>
    </section>
  );
}

function SolutionPresentation({ config, palette }: { config: ConversionBlockConfig; palette: AccentPalette | null }): JSX.Element | null {
  const loose = config as LooseConfig;
  const title = asOptionalString(loose.title);
  const text = asOptionalString(loose.text);
  const items = asStoryCards(loose.items);
  if (!title || !text || items.length === 0) return null;
  const finalTitle = asOptionalString(loose.final_title);
  const finalHighlight = asOptionalString(loose.final_highlight);
  return (
    <section className="cblock cblock--story cblock--solution" style={accentStyle(palette)}>
      {asOptionalString(loose.bridge_text) && (
        <p className="cblock__solution-bridge">{String(loose.bridge_text)}</p>
      )}
      <div className="cblock__solution-layout">
        <div className="cblock__solution-copy">
          {asOptionalString(loose.eyebrow) && <p className="cblock__story-eyebrow">{String(loose.eyebrow)}</p>}
          <StoryTitle title={title} highlight={asOptionalString(loose.highlight)} />
          <p className="cblock__story-subtitle">{text}</p>
          {asOptionalString(loose.supporting_text) && <p className="cblock__solution-support">{String(loose.supporting_text)}</p>}
        </div>
        <ul className="cblock__solution-grid">
          {items.map((item, index) => (
            <li className="cblock__story-card" key={`${item.title}-${index}`}>
              <span className="cblock__story-icon" aria-hidden="true">{STORY_ICONS[(index + 2) % STORY_ICONS.length]}</span>
              <h3>{item.title}</h3>
              {item.text && <p>{item.text}</p>}
              {item.kicker && <small>{item.kicker}</small>}
            </li>
          ))}
        </ul>
      </div>
      {(finalTitle || finalHighlight) && (
        <div className="cblock__solution-final">
          {finalTitle && <span>{finalTitle}</span>}
          {finalHighlight && <strong>{finalHighlight}</strong>}
        </div>
      )}
    </section>
  );
}

function HowItWorks({ config, palette }: { config: ConversionBlockConfig; palette: AccentPalette | null }): JSX.Element | null {
  const loose = config as LooseConfig;
  const title = asOptionalString(loose.title);
  const steps = asStoryCards(loose.steps);
  if (!title || steps.length === 0) return null;
  return (
    <section className="cblock cblock--story cblock--story-steps" style={accentStyle(palette)}>
      <div className="cblock__story-head">
        <StoryTitle title={title} highlight={asOptionalString(loose.highlight)} />
        {asOptionalString(loose.subtitle) && <p className="cblock__story-subtitle">{String(loose.subtitle)}</p>}
      </div>
      <ol className="cblock__story-timeline">
        {steps.map((step, index) => (
          <li key={`${step.title}-${index}`}>
            <span className="cblock__timeline-number">{String(index + 1).padStart(2, "0")}</span>
            <div>
              {step.kicker && <small>{step.kicker}</small>}
              <h3>{step.title}</h3>
              {step.text && <p>{step.text}</p>}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Audience({ config, palette }: { config: ConversionBlockConfig; palette: AccentPalette | null }): JSX.Element | null {
  const loose = config as LooseConfig;
  const title = asOptionalString(loose.title);
  const positiveItems = asStrings(loose.positive_items);
  const negativeItems = asStrings(loose.negative_items);
  if (!title || positiveItems.length === 0 || negativeItems.length === 0) return null;
  const columns = [
    {
      kind: "yes",
      title: asOptionalString(loose.positive_title) ?? "ES PARA TI",
      subtitle: asOptionalString(loose.positive_subtitle),
      items: positiveItems,
    },
    {
      kind: "no",
      title: asOptionalString(loose.negative_title) ?? "NO ES PARA TI",
      subtitle: asOptionalString(loose.negative_subtitle),
      items: negativeItems,
    },
  ];
  return (
    <section className="cblock cblock--story cblock--audience" style={accentStyle(palette)}>
      <div className="cblock__story-head"><StoryTitle title={title} highlight={asOptionalString(loose.highlight)} /></div>
      <div className="cblock__audience-grid">
        {columns.map((column) => (
          <article className={`cblock__audience-card cblock__audience-card--${column.kind}`} key={column.kind}>
            <header>
              <span aria-hidden="true">{column.kind === "yes" ? "✓" : "×"}</span>
              <div><h3>{column.title}</h3>{column.subtitle && <p>{column.subtitle}</p>}</div>
            </header>
            <ul>{column.items.map((item) => <li key={item}>{item}</li>)}</ul>
          </article>
        ))}
      </div>
      {asOptionalString(loose.footer) && <p className="cblock__audience-footer">{String(loose.footer)}</p>}
    </section>
  );
}

function Moment({ config, palette }: { config: ConversionBlockConfig; palette: AccentPalette | null }): JSX.Element | null {
  const loose = config as LooseConfig;
  const title = asOptionalString(loose.title);
  const highlight = asOptionalString(loose.highlight);
  const text = asOptionalString(loose.text);
  if (!title || !highlight || !text) return null;
  return (
    <section className="cblock cblock--story cblock--moment" style={accentStyle(palette)}>
      <span className="cblock__moment-rule" aria-hidden="true" />
      <StoryTitle title={title} highlight={highlight} />
      <p>{text}</p>
      {asOptionalString(loose.emphasis) && <strong className="cblock__moment-emphasis">{String(loose.emphasis)}</strong>}
      {asOptionalString(loose.footer) && <small>{String(loose.footer)}</small>}
    </section>
  );
}

/**
 * Risk reversal. With `stats`, renders as the richer store-trust badge from
 * the reference screenshots (checkmark, confidence meter, proof stats).
 * Without `stats`, renders as the original plain two-line statement.
 */
function Guarantee({
  config,
  palette,
}: {
  config: ConversionBlockConfig;
  palette: AccentPalette | null;
}): JSX.Element | null {
  if (!config.title || !config.text) return null;
  const loose = config as LooseConfig;
  const stats = asTrustStats(loose.stats);
  const benefits = asStoryCards(loose.benefits);

  if (benefits.length > 0) {
    return (
      <section className="cblock cblock--story cblock--guarantee-rich" style={accentStyle(palette)}>
        {asOptionalString(loose.eyebrow) && <p className="cblock__story-eyebrow">{String(loose.eyebrow)}</p>}
        <div className="cblock__guarantee-shield" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
            <path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3z" />
            <path d="M8.5 12.5l2.5 2.5 4.5-5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          {typeof config.days === "number" && <span>{config.days}</span>}
        </div>
        <h2 className="cblock__guarantee-rich-title">
          <span>{config.title}</span>
          {typeof config.days === "number" && <strong>Total de {config.days} días</strong>}
        </h2>
        <p className="cblock__guarantee-rich-text">{config.text}</p>
        <ul className="cblock__guarantee-benefits">
          {benefits.map((benefit, index) => (
            <li key={`${benefit.title}-${index}`}>
              <span aria-hidden="true">{STORY_ICONS[(index + 3) % STORY_ICONS.length]}</span>
              <h3>{benefit.title}</h3>
              {benefit.text && <p>{benefit.text}</p>}
            </li>
          ))}
        </ul>
      </section>
    );
  }

  if (stats.length === 0) {
    return (
      <section className="cblock cblock--guarantee" style={accentStyle(palette)}>
        <p className="cblock__guarantee-title">
          {config.title}
          {typeof config.days === "number" ? ` · ${config.days} días` : ""}
        </p>
        <p className="cblock__guarantee-text">{config.text}</p>
      </section>
    );
  }

  return (
    <section className="cblock cblock--guarantee" style={accentStyle(palette)}>
      <div className="cblock__trust-header">
        <svg className="cblock__trust-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
          <path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3z" />
          <path d="M8.5 12.5l2.5 2.5 4.5-5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <div>
          <p className="cblock__trust-title">{config.title}</p>
          <p className="cblock__trust-subtitle">{config.text}</p>
        </div>
      </div>
      <div className="cblock__trust-meter" aria-hidden="true" />
      <ul className="cblock__trust-stats">
        {stats.map((stat) => (
          <li key={stat.label}>
            {stat.value && <span className="cblock__trust-stat-value">{stat.value}</span>}
            <span className="cblock__trust-stat-label">{stat.label}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * Renders one placed component. An unknown type renders nothing rather than
 * throwing, so a payload from a newer backend degrades to the page without it.
 */
export function ConversionBlockView({
  block,
  productPrice,
  blocksDarkMode = false,
  blocksAccentPalette = null,
  ctaLabel,
  ctaAnimation = null,
  onActivateCta,
  joinPriceBefore = false,
  joinPriceAfter = false,
}: ConversionBlockViewProps): JSX.Element | null {
  const { config, accent_palette: blockPalette } = block;
  const palette = blockPalette ?? blocksAccentPalette;
  const configDark = (config as Record<string, unknown>).dark_mode;
  // Per-block dark_mode overrides the landing-level default.
  // true/false in config = explicit override; undefined/null = use landing default.
  const isDark = configDark === true ? true : configDark === false ? false : blocksDarkMode;

  let content: JSX.Element | null;
  switch (block.block_type) {
    case "cta":
      content = (
        <PurchaseCta
          config={config}
          palette={palette}
          fallbackLabel={ctaLabel}
          animation={ctaAnimation}
          onActivate={onActivateCta}
        />
      );
      break;
    case "video_carousel":
      content = <VideoCarousel block={block} palette={palette} />;
      break;
    case "announcement_bar":
      content = <AnnouncementBar config={config} palette={palette} />;
      break;
    case "cod_assurance":
      content = <CodAssurance config={config} palette={palette} />;
      break;
    case "benefits":
      content = <Benefits config={config} palette={palette} />;
      break;
    case "offer_price":
      content = <OfferPrice config={config} productPrice={productPrice} palette={palette} />;
      break;
    case "price_summary":
      content = (
        <OfferPrice
          config={config}
          productPrice={productPrice}
          palette={palette}
          mode="price"
          joinBefore={joinPriceBefore}
          joinAfter={joinPriceAfter}
        />
      );
      break;
    case "store_trust":
      content = (
        <OfferPrice
          config={config}
          productPrice={productPrice}
          palette={palette}
          mode="trust"
          joinBefore={joinPriceBefore}
          joinAfter={joinPriceAfter}
        />
      );
      break;
    case "purchase_benefits":
      content = (
        <OfferPrice
          config={config}
          productPrice={productPrice}
          palette={palette}
          mode="benefits"
          joinBefore={joinPriceBefore}
          joinAfter={joinPriceAfter}
        />
      );
      break;
    case "spacer":
      content = <Spacer />;
      break;
    case "included_benefits":
      content = <IncludedBenefits config={config} palette={palette} />;
      break;
    case "reviews":
      content = <Reviews config={config} palette={palette} />;
      break;
    case "faq":
      content = <Faq config={config} palette={palette} />;
      break;
    case "guarantee":
      content = <Guarantee config={config} palette={palette} />;
      break;
    case "main_problem":
      content = <MainProblem config={config} palette={palette} />;
      break;
    case "solution_presentation":
      content = <SolutionPresentation config={config} palette={palette} />;
      break;
    case "how_it_works":
      content = <HowItWorks config={config} palette={palette} />;
      break;
    case "audience":
      content = <Audience config={config} palette={palette} />;
      break;
    case "moment":
      content = <Moment config={config} palette={palette} />;
      break;
    default:
      content = null;
  }

  if (!content) return null;
  if (!isDark) return content;
  return <div className="cblock-dark-wrap">{content}</div>;
}
