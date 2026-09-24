/** Admin API clients for products, orders, fraud, analytics. */

import { apiClient } from "./client";
// Declared once with the public payload it describes: admin and public must
// agree on the vocabulary or the editor could save a value the page ignores.
import type {
  ConversionBlockType,
  CtaBandStyle,
  CtaColorMode,
  OfferImageAsset,
  ProductVariantOption,
  StoreSettings,
} from "./public";

/** Store settings plus operational parameters only the admin API exposes. */
export interface AdminStoreSettings extends StoreSettings {
  fulfillment_provider: "none" | "mastershop";
  mastershop_orders_url: string;
  mastershop_timeout_seconds: number;
  /** The API key itself is write-only; only its presence is reported. */
  mastershop_api_key_configured: boolean;
}

export type StoreSettingsUpdate = Partial<
  Omit<
    AdminStoreSettings,
    "logo_url" | "favicon_url" | "homepage_image_url" | "mastershop_api_key_configured"
  >
> & {
  /** Send a new value to replace the stored key, or "" to clear it. */
  mastershop_api_key?: string;
};

export const storeApi = {
  get: () => apiClient.get<AdminStoreSettings>("/admin/store"),
  update: (request: StoreSettingsUpdate) =>
    apiClient.patch<AdminStoreSettings>("/admin/store", request),
  upload: (kind: "logo" | "favicon" | "homepage_image", file: File) => {
    const form = new FormData();
    form.append("file", file);
    return apiClient.postForm<AdminStoreSettings>(`/admin/store/assets/${kind}`, form);
  },
};

// Product schemas
export interface Product {
  id: number;
  name: string;
  sku: string;
  price: number;
  description: string;
  status: "active" | "paused" | "retired";
  retired_at?: string;
  landing_id?: number | null;
  landing_slug?: string | null;
  landing_status?: string | null;
  variant_options?: ProductVariantOption[];
}

export interface ProductCreateRequest {
  name: string;
  sku: string;
  price: number;
  description?: string;
  status?: "active" | "paused";
  variant_options?: ProductVariantOption[];
}

export type ProductUpdateRequest = Partial<
  Pick<ProductCreateRequest, "name" | "sku" | "price" | "description">
>;

export interface ProductListResponse {
  products: Product[];
}

export interface MastershopProductMapping {
  id?: number;
  variant_selection: Record<string, string>;
  mastershop_product_id: number;
  mastershop_variant_id: number | null;
  weight: number;
}

export const productsApi = {
  list: async (include_retired?: boolean): Promise<ProductListResponse> => {
    const params = new URLSearchParams();
    if (include_retired) params.append("include_retired", "true");
    return apiClient.get<ProductListResponse>(`/admin/products?${params}`);
  },

  get: async (id: number): Promise<Product> => {
    return apiClient.get<Product>(`/admin/products/${id}`);
  },

  create: async (request: ProductCreateRequest): Promise<Product> => {
    return apiClient.post<Product>("/admin/products", request);
  },

  update: async (id: number, request: ProductUpdateRequest): Promise<Product> => {
    return apiClient.patch<Product>(`/admin/products/${id}`, request);
  },

  activate: async (id: number): Promise<Product> => {
    return apiClient.post<Product>(`/admin/products/${id}/activate`);
  },

  pause: async (id: number): Promise<Product> => {
    return apiClient.post<Product>(`/admin/products/${id}/pause`);
  },

  delete: async (id: number): Promise<void> => {
    return apiClient.delete(`/admin/products/${id}`);
  },

  getMastershopMappings: async (id: number): Promise<{ mappings: MastershopProductMapping[] }> => {
    return apiClient.get(`/admin/products/${id}/mastershop-mappings`);
  },

  replaceMastershopMappings: async (
    id: number,
    mappings: MastershopProductMapping[],
  ): Promise<{ mappings: MastershopProductMapping[] }> => {
    return apiClient.put(`/admin/products/${id}/mastershop-mappings`, { mappings });
  },
};

// Order schemas
export interface Order {
  id: number;
  product_id: number;
  landing_id: number;
  landing_slug: string;
  customer_name: string;
  phone_e164: string;
  phone_normalized_key?: string;
  department: string;
  city: string;
  address: string;
  quantity: number;
  variant_selections?: Record<string, string>[];
  unit_price: number;
  discount_percent: number;
  total_price: number;
  product_name?: string;
  product_sku?: string;
  status: "pending" | "confirmed" | "shipped" | "delivered" | "cancelled" | "flagged_fraud";
  ip_address: string;
  user_agent: string;
  created_at: string;
  updated_at: string;
  fraud_flags?: FraudFlag[];
  fulfillment_details?: OrderFulfillmentDetails | null;
  mastershop_sync?: MastershopOrderSync | null;
}

export interface OrderFulfillmentDetails {
  first_name: string;
  last_name: string;
  address1: string;
  address2: string | null;
}

export interface MastershopOrderSync {
  status: "pending" | "syncing" | "success" | "failed" | "waiting_review";
  attempt_count: number;
  response_status: number | null;
  response_body: unknown;
  last_error: string | null;
  last_attempt_at: string | null;
  synced_at: string | null;
  updated_at: string;
}

export interface OrderFulfillmentUpdateRequest {
  first_name: string;
  last_name: string;
  phone: string;
  department: string;
  city: string;
  address1: string;
  address2?: string | null;
}

export interface FraudFlag {
  id?: number;
  flag_type: "duplicate" | "blacklist" | "rate_limit_phone" | "rate_limit_ip" | "geoip";
  detail: Record<string, unknown>;
  created_at?: string;
}

export interface OrderListResponse {
  orders: Order[];
  count: number;
}

export interface OrderTransitionRequest {
  to_status: "confirmed" | "shipped" | "delivered" | "cancelled" | "pending";
}

export interface OrderTransitionResponse {
  order_id: number;
  status: Order["status"];
}

export const ordersApi = {
  list: async (params?: {
    status?: string;
    product_id?: number;
    landing_id?: number;
    date_from?: string;
    date_to?: string;
  }): Promise<OrderListResponse> => {
    const query = new URLSearchParams();
    if (params?.status) query.append("status", params.status);
    if (params?.product_id) query.append("product_id", params.product_id.toString());
    if (params?.landing_id) query.append("landing_id", params.landing_id.toString());
    if (params?.date_from) query.append("date_from", params.date_from);
    if (params?.date_to) query.append("date_to", params.date_to);
    return apiClient.get<OrderListResponse>(`/admin/orders?${query}`);
  },

  get: async (id: number): Promise<Order> => {
    return apiClient.get<Order>(`/admin/orders/${id}`);
  },

  transition: async (
    id: number,
    request: OrderTransitionRequest,
  ): Promise<OrderTransitionResponse> => {
    return apiClient.post<OrderTransitionResponse>(`/admin/orders/${id}/transition`, request);
  },

  updateFulfillment: async (
    id: number,
    request: OrderFulfillmentUpdateRequest,
  ): Promise<Order> => {
    return apiClient.patch<Order>(`/admin/orders/${id}/fulfillment`, request);
  },

  retryMastershop: async (
    id: number,
  ): Promise<{ order_id: number; mastershop_sync: MastershopOrderSync }> => {
    return apiClient.post(`/admin/orders/${id}/mastershop/retry`, {});
  },

  export: async (params?: {
    status?: string;
    product_id?: number;
    landing_id?: number;
    date_from?: string;
    date_to?: string;
  }): Promise<Blob> => {
    const query = new URLSearchParams();
    if (params?.status) query.append("status", params.status);
    if (params?.product_id) query.append("product_id", params.product_id.toString());
    if (params?.landing_id) query.append("landing_id", params.landing_id.toString());
    if (params?.date_from) query.append("date_from", params.date_from);
    if (params?.date_to) query.append("date_to", params.date_to);
    return apiClient.getBlob(`/admin/orders/export.csv?${query}`);
  },
};

// Fraud schemas
export interface FraudConfig {
  id: number;
  duplicate_window_hours: number;
  duplicate_match_fields: string[];
  rate_limit_max: number;
  rate_limit_window_minutes: number;
  banned_cities?: string[];
}

export interface FraudConfigUpdate {
  duplicate_window_hours?: number;
  duplicate_match_fields?: string[];
  rate_limit_max?: number;
  rate_limit_window_minutes?: number;
  banned_cities?: string[];
}

export interface BlacklistEntry {
  id: number;
  entry_type: "phone" | "ip";
  value_normalized: string;
  reason: string;
  created_at: string;
}

export interface BlacklistEntryCreate {
  entry_type: "phone" | "ip";
  value_normalized: string;
  reason: string;
}

export interface GeoIpRule {
  id: number;
  location_code: string;
  action: "flag" | "block";
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface GeoIpRuleCreate {
  location_code: string;
  action: "flag" | "block";
  enabled?: boolean;
}

export interface BlacklistEntryListResponse {
  entries: BlacklistEntry[];
}

export interface GeoIpRuleListResponse {
  rules: GeoIpRule[];
}

export const fraudApi = {
  getConfig: async (): Promise<FraudConfig> => {
    return apiClient.get<FraudConfig>("/admin/fraud/config");
  },

  updateConfig: async (request: FraudConfigUpdate): Promise<FraudConfig> => {
    return apiClient.put<FraudConfig>("/admin/fraud/config", request);
  },

  listBlacklist: async (): Promise<BlacklistEntryListResponse> => {
    return apiClient.get<BlacklistEntryListResponse>("/admin/fraud/blacklist");
  },

  addBlacklistEntry: async (request: BlacklistEntryCreate): Promise<BlacklistEntry> => {
    return apiClient.post<BlacklistEntry>("/admin/fraud/blacklist", request);
  },

  removeBlacklistEntry: async (id: number): Promise<{ message: string }> => {
    return apiClient.delete<{ message: string }>(`/admin/fraud/blacklist/${id}`);
  },

  listGeoIpRules: async (): Promise<GeoIpRuleListResponse> => {
    return apiClient.get<GeoIpRuleListResponse>("/admin/fraud/geoip-rules");
  },

  createGeoIpRule: async (request: GeoIpRuleCreate): Promise<GeoIpRule> => {
    return apiClient.post<GeoIpRule>("/admin/fraud/geoip-rules", request);
  },

  updateGeoIpRule: async (
    id: number,
    request: Partial<GeoIpRuleCreate>,
  ): Promise<GeoIpRule> => {
    return apiClient.patch<GeoIpRule>(`/admin/fraud/geoip-rules/${id}`, request);
  },

  deleteGeoIpRule: async (id: number): Promise<{ message: string }> => {
    return apiClient.delete<{ message: string }>(`/admin/fraud/geoip-rules/${id}`);
  },
};

// Analytics schemas
export interface OrdersPerDay {
  date: string;
  count: number;
}

export interface LandingAnalytics {
  landing_id: number;
  views: number;
  clicks: number;
  orders: number;
  conversion_rate: number;
}

export interface FraudAnalytics {
  date: string;
  flagged_orders: number;
  total_orders: number;
  flagged_fraud_rate: number;
}

export const analyticsApi = {
  getOrdersPerDay: async (date_from: string, date_to: string): Promise<OrdersPerDay[]> => {
    const params = new URLSearchParams({ date_from, date_to });
    return apiClient.get<OrdersPerDay[]>(`/admin/analytics/orders-per-day?${params}`);
  },

  getLandingAnalytics: async (
    date_from: string,
    date_to: string,
    landing_id?: number,
  ): Promise<LandingAnalytics[]> => {
    const params = new URLSearchParams({ date_from, date_to });
    if (landing_id !== undefined) params.append("landing_id", landing_id.toString());
    return apiClient.get<LandingAnalytics[]>(`/admin/analytics/landings?${params}`);
  },

  getFraudAnalytics: async (date_from: string, date_to: string): Promise<FraudAnalytics[]> => {
    const params = new URLSearchParams({ date_from, date_to });
    return apiClient.get<FraudAnalytics[]>(`/admin/analytics/fraud?${params}`);
  },
};

// Landing schemas (Requirement 8.3)
export type CtaMode = "after_every" | "every_n" | "fixed_positions";
export type FormPresentation = "inline" | "modal";

export interface LandingImageVariant {
  width: number;
  height: number;
  format: string;
  url: string;
}

export interface LandingBanner {
  id: number;
  alt_text: string;
  order_index: number;
  image_asset_id: number;
  image_status: string;
  variants: LandingImageVariant[];
}

/**
 * One configured quantity offer, as the dashboard reads and writes it.
 *
 * `sublabel` blank means the public tile renders no second line — that is the
 * documented way to turn the sub-text off, not an incomplete field.
 * Multi-unit offers accept either `discount_percent` or `discount_amount`;
 * `compare_at_price` is informational and only applies to one unit.
 */
export interface LandingOffer {
  quantity: number;
  label: string;
  sublabel: string | null;
  discount_percent: number;
  discount_amount?: number | null;
  calculated_discount_percent?: number;
  compare_at_price: number | null;
}

export interface LandingSummary {
  id: number;
  product_id: number;
  product_name: string;
  product_sku: string;
  product_status: string;
  slug: string;
  status: "draft" | "published";
  cta_mode: CtaMode;
  cta_interval: number | null;
  cta_positions: number[];
  form_presentation: FormPresentation;
  cta_band_style: CtaBandStyle;
  /** The one color the merchant controls on the public page, as `#rrggbb`. */
  accent_color: string;
  /** The COD form's own accent. Null means it follows `accent_color`. */
  form_accent_color: string | null;
  /** Default conversion-block accent. Null means it follows the form accent. */
  blocks_accent_color?: string | null;
  /** How many quantity offers the COD form presents (1-3). */
  offer_count: number;
  default_offer_quantity?: number;
  offers: LandingOffer[];
  banner_count: number;
  cta_text: string | null;
  cta_animation: "slide" | "shake" | null;
  /**
   * Per-CTA-position text override, keyed by 1-based position as a string
   * (e.g. `{"2": "Lo quiero ahora"}`). A position absent here uses `cta_text`
   * (or the default label) instead.
   */
  cta_text_overrides: Record<string, string>;
  cta_color_modes?: Record<string, Exclude<CtaColorMode, "default">>;
  blocks_dark_mode: boolean;
}

export interface LandingDetail extends LandingSummary {
  banners: LandingBanner[];
  resolved_cta_positions: number[];
}

export interface LandingListResponse {
  landings: LandingSummary[];
}

export interface BannerListResponse {
  banners: LandingBanner[];
}

/**
 * One offer as submitted by the dashboard. `sublabel` is sent as an empty string
 * to mean "no sub-text", and discount/reference amounts are sent as `null`
 * when the merchant cleared them.
 */
export interface LandingOfferUpdate {
  quantity: number;
  label: string;
  sublabel: string | null;
  discount_percent: number | null;
  discount_amount: number | null;
  compare_at_price: number | null;
}

export interface LandingConfigUpdate {
  slug?: string;
  cta_mode?: CtaMode;
  cta_interval?: number | null;
  cta_positions?: number[];
  form_presentation?: FormPresentation;
  cta_band_style?: CtaBandStyle;
  accent_color?: string;
  form_accent_color?: string | null;
  blocks_accent_color?: string | null;
  offer_count?: number;
  default_offer_quantity?: number;
  offers?: LandingOfferUpdate[];
  cta_text?: string | null;
  cta_animation?: "slide" | "shake" | null;
  cta_text_overrides?: Record<string, string>;
  cta_color_modes?: Record<string, Exclude<CtaColorMode, "default">>;
  blocks_dark_mode?: boolean;
}

/**
 * Pre-defined conversion components. The vocabulary is closed and their
 * presentation is fixed in the landing chrome, so the dashboard edits content
 * and position only. The type union is declared once, in `./public`, since the
 * public payload and the dashboard describe the same components.
 */
export interface LandingBlock {
  id: number;
  block_type: ConversionBlockType;
  /** How many rendered elements the component follows (0 = above everything). */
  slot_index: number;
  order_index: number;
  enabled: boolean;
  config: Record<string, unknown>;
  videos?: LandingBlockVideo[];
  offer_images?: OfferImageAsset[];
}

export interface LandingBlockVideo {
  id: number;
  url: string;
  poster_url: string;
  width: number;
  height: number;
  duration_ms: number;
  byte_size: number;
  order_index: number;
  caption: string | null;
}

export interface LandingBlockListResponse {
  blocks: LandingBlock[];
  /** One label per placement slot, index 0 first (e.g. "1-2 · entre banner 1 y CTA 1"). */
  slots: string[];
  allowed_block_types: ConversionBlockType[];
}

/**
 * A saved snapshot of one landing's configuration, reusable on another product.
 *
 * `banner_count` is both a description and a precondition: it is how many
 * banners the source landing had, and a template only loads onto a landing with
 * exactly that many, because the stored CTA positions and component slots
 * address places in the rendered banner/CTA sequence.
 */
export interface LandingTemplate {
  id: number;
  name: string;
  banner_count: number;
  /** How many conversion components the template carries. */
  block_count: number;
  created_at: string;
  updated_at: string;
}

export interface LandingTemplateListResponse {
  templates: LandingTemplate[];
}

export const landingTemplatesApi = {
  list: async (): Promise<LandingTemplateListResponse> => {
    return apiClient.get<LandingTemplateListResponse>("/admin/landing-templates");
  },

  /**
   * Snapshot a landing's configuration under `name`.
   *
   * Rejects with a 409 `ApiError` when the name is taken and `overwrite` is
   * false, so the caller can ask before replacing an existing template.
   */
  save: async (request: {
    landing_id: number;
    name: string;
    overwrite?: boolean;
  }): Promise<LandingTemplate> => {
    return apiClient.post<LandingTemplate>("/admin/landing-templates", request);
  },

  remove: async (templateId: number): Promise<LandingTemplateListResponse> => {
    return apiClient.delete<LandingTemplateListResponse>(
      `/admin/landing-templates/${templateId}`,
    );
  },
};

export const landingsApi = {
  list: async (include_retired?: boolean): Promise<LandingListResponse> => {
    const params = new URLSearchParams();
    if (include_retired) params.append("include_retired", "true");
    return apiClient.get<LandingListResponse>(`/admin/landings?${params}`);
  },

  get: async (id: number): Promise<LandingDetail> => {
    return apiClient.get<LandingDetail>(`/admin/landings/${id}`);
  },

  updateConfig: async (id: number, request: LandingConfigUpdate): Promise<LandingDetail> => {
    return apiClient.patch<LandingDetail>(`/admin/landings/${id}`, request);
  },

  /** Multipart banner upload: the image pipeline runs server-side. */
  uploadBanner: async (id: number, file: File, altText: string): Promise<LandingBanner> => {
    const form = new FormData();
    form.append("file", file);
    form.append("alt_text", altText);
    return apiClient.postForm<LandingBanner>(`/admin/landings/${id}/banners`, form);
  },

  updateBanner: async (
    id: number,
    bannerId: number,
    request: { alt_text?: string; order_index?: number },
  ): Promise<BannerListResponse> => {
    return apiClient.patch<BannerListResponse>(
      `/admin/landings/${id}/banners/${bannerId}`,
      request,
    );
  },

  reorderBanners: async (id: number, bannerIds: number[]): Promise<BannerListResponse> => {
    return apiClient.put<BannerListResponse>(`/admin/landings/${id}/banners/order`, {
      banner_ids: bannerIds,
    });
  },

  deleteBanner: async (id: number, bannerId: number): Promise<BannerListResponse> => {
    return apiClient.delete<BannerListResponse>(`/admin/landings/${id}/banners/${bannerId}`);
  },

  publish: async (id: number): Promise<LandingDetail> => {
    return apiClient.post<LandingDetail>(`/admin/landings/${id}/publish`);
  },

  unpublish: async (id: number): Promise<LandingDetail> => {
    return apiClient.post<LandingDetail>(`/admin/landings/${id}/unpublish`);
  },

  /**
   * Apply a saved template's configuration and components to this landing.
   *
   * Returns the updated landing so the editor re-renders from one round trip.
   * Rejects with a 422 `ApiError` carrying a `banner_count` field error when the
   * landing's banner count does not match the template's.
   */
  loadTemplate: async (id: number, templateId: number): Promise<LandingDetail> => {
    return apiClient.post<LandingDetail>(`/admin/landings/${id}/load-template`, {
      template_id: templateId,
    });
  },

  listBlocks: async (id: number): Promise<LandingBlockListResponse> => {
    return apiClient.get<LandingBlockListResponse>(`/admin/landings/${id}/blocks`);
  },

  createBlock: async (
    id: number,
    request: {
      block_type: ConversionBlockType;
      slot_index: number;
      config: Record<string, unknown>;
      enabled?: boolean;
    },
  ): Promise<LandingBlockListResponse> => {
    return apiClient.post<LandingBlockListResponse>(`/admin/landings/${id}/blocks`, request);
  },

  updateBlock: async (
    id: number,
    blockId: number,
    request: {
      slot_index?: number;
      config?: Record<string, unknown>;
      enabled?: boolean;
    },
  ): Promise<LandingBlockListResponse> => {
    return apiClient.patch<LandingBlockListResponse>(
      `/admin/landings/${id}/blocks/${blockId}`,
      request,
    );
  },

  reorderBlocks: async (id: number, blockIds: number[]): Promise<LandingBlockListResponse> => {
    return apiClient.patch<LandingBlockListResponse>(`/admin/landings/${id}/blocks/order`, {
      block_ids: blockIds,
    });
  },

  deleteBlock: async (id: number, blockId: number): Promise<LandingBlockListResponse> => {
    return apiClient.delete<LandingBlockListResponse>(`/admin/landings/${id}/blocks/${blockId}`);
  },

  uploadBlockVideo: async (
    id: number,
    blockId: number,
    file: File,
    caption: string,
  ): Promise<LandingBlockListResponse> => {
    const form = new FormData();
    form.append("file", file);
    form.append("caption", caption);
    return apiClient.postForm<LandingBlockListResponse>(
      `/admin/landings/${id}/blocks/${blockId}/videos`,
      form,
    );
  },

  deleteBlockVideo: async (
    id: number,
    blockId: number,
    videoId: number,
  ): Promise<LandingBlockListResponse> => {
    return apiClient.delete<LandingBlockListResponse>(
      `/admin/landings/${id}/blocks/${blockId}/videos/${videoId}`,
    );
  },

  uploadBlockOfferImage: async (
    id: number,
    blockId: number,
    quantity: number,
    file: File,
  ): Promise<LandingBlockListResponse> => {
    const form = new FormData();
    form.append("file", file);
    return apiClient.postForm<LandingBlockListResponse>(
      `/admin/landings/${id}/blocks/${blockId}/offer-images/${quantity}`,
      form,
    );
  },

  deleteBlockOfferImage: async (
    id: number,
    blockId: number,
    quantity: number,
  ): Promise<LandingBlockListResponse> => {
    return apiClient.delete<LandingBlockListResponse>(
      `/admin/landings/${id}/blocks/${blockId}/offer-images/${quantity}`,
    );
  },
};
