/** Public landing and checkout API clients. */

import { apiClient } from "./client";

export interface Banner {
  id: number;
  alt_text: string;
  order_index: number;
  variants: {
    width: number;
    height: number;
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
/** Per-position CTA band treatment. Default keeps banner-derived colors. */
export type CtaColorMode = "default" | "dark" | "light";

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
 * elements. The type is a closed vocabulary; `config` carries content plus,
 * for every type, an optional `accent_color` override — everything else
 * (spacing, type, layout) is fixed in the landing chrome and tuned for
 * conversion.
 */
export type ConversionBlockType =
  | "cta"
  | "video_carousel"
  | "announcement_bar"
  | "cod_assurance"
  | "benefits"
  | "offer_price"
  | "included_benefits"
  | "reviews"
  | "faq"
  | "guarantee"
  | "main_problem"
  | "solution_presentation"
  | "how_it_works"
  | "audience"
  | "moment";

export interface ConversionBlockConfig {
  title?: string | null;
  note?: string | null;
  items?: unknown[];
  steps?: unknown[];
  text?: string | null;
  days?: number | null;
  compare_at_price?: number | null;
  /**
   * Optional per-component accent override (`#rrggbb`). When absent, the
   * component inherits the landing's form accent color. Present on every
   * block type — it is a bounded content field, not a presentation escape
   * hatch: it only ever recolors the buttons/lines/background this
   * component already draws with the accent token.
   */
  accent_color?: string | null;
  /**
   * Additive fields for newer block variants (comparison rows, urgency
   * items, trust stats, delivery dates, etc.) are stored in the same JSON
   * config blob but differ per block type. An index signature allows the
   * frontend to read them without duplicating the union of every possible
   * key as explicit optional properties.
   */
  [key: string]: unknown;
}

export interface ConversionBlock {
  id: number;
  block_type: ConversionBlockType;
  /** How many rendered elements this component follows (0 = above everything). */
  slot_index: number;
  order_index: number;
  config: ConversionBlockConfig;
  /**
   * Full derived palette for this component's `accent_color` override,
   * computed server-side (same math as the landing's own accent) so the
   * client never picks an unreadable foreground. `null` when the component
   * has no override and inherits the page's form accent.
   */
  accent_palette: AccentPalette | null;
  videos?: VideoAsset[];
}

export interface VideoAsset {
  id: number;
  url: string;
  poster_url: string;
  width: number;
  height: number;
  duration_ms: number;
  caption: string | null;
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
  discount_amount?: number | null;
  unit_price: number;
  gross: number;
  total: number;
  savings: number;
  compare_at_price: number | null;
}

export interface ProductVariantOption {
  name: string;
  values: string[];
}

export interface ColombianCity {
  code: string;
  name: string;
}

export interface ColombianDepartment {
  code: string;
  name: string;
  cities: ColombianCity[];
}

export interface LocationCatalog {
  departments: ColombianDepartment[];
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
  /** Landing-level dark mode default for all conversion blocks. */
  blocks_dark_mode?: boolean;
  /** Absent on payloads cached before per-landing accents existed. */
  accent_color?: string;
  accent_palette?: AccentPalette;
  /**
   * The COD form's own accent, independent of the CTA's. Absent on payloads
   * cached before this existed, in which case the form follows `accent_color`.
   */
  form_accent_color?: string;
  form_accent_palette?: AccentPalette;
  /** Default block accent; absent cached payloads fall back to the form accent. */
  blocks_accent_color?: string;
  blocks_accent_palette?: AccentPalette;
  /** Absent on payloads cached before configurable offers existed. */
  offers?: PublicLandingOffer[];
  default_offer_quantity?: number;
  variant_options?: ProductVariantOption[];
  /** Custom CTA button text. Null means use default label. */
  cta_text?: string | null;
  /** CTA animation: "slide" (left-to-right) or "shake". Null means no animation. */
  cta_animation?: "slide" | "shake" | null;
  /**
   * Per-CTA-position text override, keyed by 1-based position as a string
   * (e.g. `{"2": "Lo quiero ahora"}`). A position absent here renders
   * `cta_text` (or the default label) instead. Absent entirely on payloads
   * cached before this existed.
   */
  cta_text_overrides?: Record<string, string>;
  /** Missing positions use the automatic banner-derived background. */
  cta_color_modes?: Record<string, Exclude<CtaColorMode, "default">>;
}

export interface OrderCreateRequest {
  landing_slug: string;
  full_name: string;
  phone: string;
  department: string;
  city: string;
  address: string;
  quantity: number;
  variant_selections?: Record<string, string>[];
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

  getLocations: async (): Promise<LocationCatalog> => {
    return apiClient.get<LocationCatalog>("/public/locations");
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
