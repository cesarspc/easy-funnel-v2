/**
 * The eight pre-defined conversion components a landing can place, including
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
 * What each one is for, against cold cash-on-delivery traffic on a phone:
 *
 * - `announcement_bar` — the first thing a visitor sees, above the hero
 *   banner: one line (free shipping, a promo window) in a bar that is its own
 *   accent surface.
 * - `cod_assurance` — removes the payment objection at the moment it appears.
 *   Its three points are platform facts (pay on delivery, check first, no card),
 *   so they are fixed copy; only a merchant note is configurable.
 * - `benefits` — turns product features into reasons, scannable in one pass.
 * - `offer_price` — states price and, when the merchant declares a reference
 *   price, the saving. The selling price always comes from the product, so it
 *   cannot disagree with what the order charges.
 * - `how_it_works` — three steps, because "what happens after I submit?" is the
 *   second objection after price for COD buyers.
 * - `reviews` — social proof with a name and city; the merchant supplies real
 *   ones, this renders them.
 * - `faq` — native `<details>` accordion: answers objections without pushing the
 *   CTA off the screen.
 * - `guarantee` — risk reversal, stated once, plainly.
 */

import type { CSSProperties, JSX } from "react";
import type { AccentPalette, ConversionBlock, ConversionBlockConfig } from "../../api";
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
}

function asStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
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
    "--lp-action": accent,
    "--lp-action-deep": deep,
    "--lp-action-tint": tint,
    "--lp-action-ink": ink,
    "--lp-form-action": accent,
    "--lp-form-action-deep": deep,
    "--lp-form-action-tint": tint,
    "--lp-form-action-ink": ink,
  };
  return style as CSSProperties;
}

interface ReviewItem {
  name: string;
  city?: string | null;
  text: string;
  rating?: number | null;
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
      },
    ];
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

function BlockHeading({ title }: { title?: string | null }): JSX.Element | null {
  if (!title) return null;
  return <h2 className="cblock__title">{title}</h2>;
}

/** Top-of-page bar: one line, its own accent as background. */
function AnnouncementBar({
  config,
  palette,
}: {
  config: ConversionBlockConfig;
  palette: AccentPalette | null;
}): JSX.Element | null {
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
  return (
    <section
      className="cblock cblock--assurance"
      style={accentStyle(palette)}
      aria-label="Pago contraentrega"
    >
      <ul className="cblock__assurances">
        <li>
          <strong>Pagas al recibir</strong>
          <span>En efectivo, cuando el pedido llega a tu puerta.</span>
        </li>
        <li>
          <strong>Revisas antes de pagar</strong>
          <span>Ves el producto con el mensajero presente.</span>
        </li>
        <li>
          <strong>Sin tarjeta</strong>
          <span>No pedimos datos bancarios en ningún momento.</span>
        </li>
      </ul>
      {config.note && <p className="cblock__note">{config.note}</p>}
    </section>
  );
}

function Benefits({
  config,
  palette,
}: {
  config: ConversionBlockConfig;
  palette: AccentPalette | null;
}): JSX.Element | null {
  const items = asStrings(config.items);
  if (items.length === 0) return null;
  return (
    <section className="cblock cblock--benefits" style={accentStyle(palette)}>
      <BlockHeading title={config.title ?? "Por qué lo vas a querer"} />
      <ul className="cblock__benefits">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

function OfferPrice({
  config,
  productPrice,
  palette,
}: {
  config: ConversionBlockConfig;
  productPrice: number;
  palette: AccentPalette | null;
}): JSX.Element {
  const compareAt =
    typeof config.compare_at_price === "number" && config.compare_at_price > productPrice
      ? config.compare_at_price
      : null;
  const savings = compareAt === null ? null : compareAt - productPrice;
  const percent =
    compareAt === null || savings === null ? null : Math.round((savings / compareAt) * 100);

  return (
    <section className="cblock cblock--price" style={accentStyle(palette)} aria-label="Precio">
      <p className="cblock__price-row">
        {compareAt !== null && (
          <span className="cblock__price-was">
            <span className="sr-only">Antes </span>
            {CURRENCY.format(compareAt)}
          </span>
        )}
        <span className="cblock__price-now">{CURRENCY.format(productPrice)}</span>
      </p>
      {savings !== null && percent !== null && (
        <p className="cblock__price-save">
          Ahorras {CURRENCY.format(savings)} ({percent}%)
        </p>
      )}
      {config.note && <p className="cblock__note">{config.note}</p>}
    </section>
  );
}

function HowItWorks({
  config,
  palette,
}: {
  config: ConversionBlockConfig;
  palette: AccentPalette | null;
}): JSX.Element | null {
  const steps = asStrings(config.steps);
  if (steps.length === 0) return null;
  return (
    <section className="cblock cblock--steps" style={accentStyle(palette)}>
      <BlockHeading title={config.title ?? "Cómo funciona"} />
      <ol className="cblock__steps">
        {steps.map((step, index) => (
          <li key={step}>
            <span className="cblock__step-number" aria-hidden="true">
              {index + 1}
            </span>
            <span className="cblock__step-text">{step}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Reviews({
  config,
  palette,
}: {
  config: ConversionBlockConfig;
  palette: AccentPalette | null;
}): JSX.Element | null {
  const items = asReviews(config.items);
  if (items.length === 0) return null;
  return (
    <section className="cblock cblock--reviews" style={accentStyle(palette)}>
      <BlockHeading title={config.title ?? "Lo que dicen los clientes"} />
      <ul className="cblock__reviews">
        {items.map((review) => (
          <li key={`${review.name}-${review.text}`} className="cblock__review">
            {typeof review.rating === "number" && (
              <p className="cblock__rating" aria-label={`${review.rating} de 5 estrellas`}>
                <span aria-hidden="true">{"★".repeat(review.rating)}</span>
                <span aria-hidden="true" className="cblock__rating-empty">
                  {"★".repeat(Math.max(0, 5 - review.rating))}
                </span>
              </p>
            )}
            <blockquote className="cblock__review-text">{review.text}</blockquote>
            <p className="cblock__review-author">
              {review.name}
              {review.city ? ` · ${review.city}` : ""}
            </p>
          </li>
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

function Guarantee({
  config,
  palette,
}: {
  config: ConversionBlockConfig;
  palette: AccentPalette | null;
}): JSX.Element | null {
  if (!config.title || !config.text) return null;
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

/**
 * Renders one placed component. An unknown type renders nothing rather than
 * throwing, so a payload from a newer backend degrades to the page without it.
 */
export function ConversionBlockView({
  block,
  productPrice,
}: ConversionBlockViewProps): JSX.Element | null {
  const { config, accent_palette: palette } = block;

  switch (block.block_type) {
    case "announcement_bar":
      return <AnnouncementBar config={config} palette={palette} />;
    case "cod_assurance":
      return <CodAssurance config={config} palette={palette} />;
    case "benefits":
      return <Benefits config={config} palette={palette} />;
    case "offer_price":
      return <OfferPrice config={config} productPrice={productPrice} palette={palette} />;
    case "how_it_works":
      return <HowItWorks config={config} palette={palette} />;
    case "reviews":
      return <Reviews config={config} palette={palette} />;
    case "faq":
      return <Faq config={config} palette={palette} />;
    case "guarantee":
      return <Guarantee config={config} palette={palette} />;
    default:
      return null;
  }
}
