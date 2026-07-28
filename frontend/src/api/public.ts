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
