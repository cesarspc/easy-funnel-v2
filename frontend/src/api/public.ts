/** Public landing and checkout API clients. */

import { apiClient } from "./client";

export interface Banner {
  id: number;
  alt_text: string;
  order_index: number;
  variants: {
    width: number;
    format: "webp" | "jpeg";
    url: string;
  }[];
  top_edge_color: string | null;
  bottom_edge_color: string | null;
}

export type CtaBackgroundSource = "blend" | "above" | "below" | "fallback";
export type CtaForegroundMode = "light" | "dark" | null;

/**
 * How the landing paints its CTA bands. `gradient` fades between the two
 * neighbouring banner edges; `solid` fills the band with `blend_color`, the
 * midpoint of those edges. The colors in `cta_backgrounds` are the same
 * either way — this only selects how they are applied.
 */
export type CtaBandStyle = "gradient" | "solid";

export interface CtaBackground {
  position: number;
  top_color: string | null;
  bottom_color: string | null;
  blend_color: string | null;
  foreground: CtaForegroundMode;
  source: CtaBackgroundSource;
}

/**
 * Pre-defined conversion components a landing can place between its rendered
 * elements. The type is a closed vocabulary; `config` carries content only,
 * because every component's spacing, type, and color are fixed in the landing
 * chrome and tuned for conversion.
 */
export type ConversionBlockType =
  | "cod_assurance"
  | "benefits"
  | "offer_price"
  | "how_it_works"
  | "reviews"
  | "faq"
  | "guarantee";

export interface ConversionBlockConfig {
  title?: string | null;
  note?: string | null;
  items?: unknown[];
  steps?: string[];
  text?: string | null;
  days?: number | null;
  compare_at_price?: number | null;
}

export interface ConversionBlock {
  id: number;
  block_type: ConversionBlockType;
  /** How many rendered elements this component follows (0 = above everything). */
  slot_index: number;
  order_index: number;
  config: ConversionBlockConfig;
}

/**
 * The landing's accent and every shade the chrome derives from it. Computed
 * server-side so the page never does color math and the merchant can never pick
 * a combination that fails contrast: `ink` is chosen against `accent`.
 */
export interface AccentPalette {
  accent: string;
  deep: string;
  tint: string;
  ink: string;
}

/**
 * One quantity offer the COD form presents, already priced by the backend.
 *
 * `total` is what the buyer owes and what the order records. `gross`/`savings`
 * let a discounted tier show its pre-discount price without recomputing money
 * client-side. `sublabel` is `null` when the merchant left the sub-text blank,
 * meaning the tile renders no second line. `compare_at_price` is informational
 * only and exists on the single-unit offer alone.
 */
export interface PublicLandingOffer {
  quantity: number;
  label: string;
  sublabel: string | null;
  discount_percent: number;
  unit_price: number;
  gross: number;
  total: number;
  savings: number;
  compare_at_price: number | null;
}

export interface PublicLanding {
  landing_id: number;
  product_id: number;
  product_name: string;
  product_sku: string;
  product_price: number;
  slug: string;
  banners: Banner[];
  cta_positions: number[];
  cta_backgrounds: CtaBackground[];
  form_presentation: "inline" | "modal";
  /** Absent on payloads cached before the setting existed; treated as `gradient`. */
  cta_band_style?: CtaBandStyle;
  /** Absent on payloads cached before conversion components existed. */
  blocks?: ConversionBlock[];
  /** Absent on payloads cached before per-landing accents existed. */
  accent_color?: string;
  accent_palette?: AccentPalette;
  /** Absent on payloads cached before configurable offers existed. */
  offers?: PublicLandingOffer[];
}

export interface OrderCreateRequest {
  landing_slug: string;
  full_name: string;
  phone: string;
  department: string;
  city: string;
  address: string;
  quantity: number;
}

export interface OrderCreateResponse {
  order_id: number;
  status: "pending" | "flagged_fraud";
}

export const publicApi = {
  /**
   * Fetch a public landing by slug.
   * Returns identical 404 for unknown, draft, paused, or retired slugs.
   */
  getLanding: async (slug: string): Promise<PublicLanding> => {
    return apiClient.get<PublicLanding>(`/public/landings/${encodeURIComponent(slug)}`);
  },

  /**
   * Record a landing view.
   */
  recordView: async (slug: string): Promise<void> => {
    return apiClient.post(`/public/landings/${encodeURIComponent(slug)}/view`);
  },

  /**
   * Record a CTA click.
   */
  recordCtaClick: async (slug: string): Promise<void> => {
    return apiClient.post(`/public/landings/${encodeURIComponent(slug)}/cta-click`);
  },

  /**
   * Submit a COD order.
   */
  createOrder: async (request: OrderCreateRequest): Promise<OrderCreateResponse> => {
    return apiClient.post<OrderCreateResponse>("/public/orders", request);
  },
};
