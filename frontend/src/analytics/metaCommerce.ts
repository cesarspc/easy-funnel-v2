/**
 * Storefront commerce events consumed by the existing GTM web container.
 *
 * The container maps GA4 ecommerce names (`begin_checkout`, `purchase`) to
 * Meta's standard InitiateCheckout/Purchase events, sends the browser event,
 * and relays the same GTM event to Stape's server container. Event IDs remain
 * owned by the container's shared Unique Event ID variable so browser and CAPI
 * receive the same value for deduplication.
 */

import type { PublicLanding, PublicLandingOffer } from "../api";
import { type RegionalSettings, toE164 } from "../features/store/regional";

interface DataLayerWindow extends Window {
  dataLayer?: Record<string, unknown>[];
}

export interface PurchaseCustomerData {
  firstName: string;
  lastName: string;
  phone: string;
  city: string;
  state: string;
}

export interface PurchaseEventData extends PurchaseCustomerData {
  orderId: number;
  quantity: number;
  value: number;
}

function dataLayer(): Record<string, unknown>[] {
  const browserWindow = window as DataLayerWindow;
  browserWindow.dataLayer = browserWindow.dataLayer ?? [];
  return browserWindow.dataLayer;
}

function offerForCheckout(landing: PublicLanding): PublicLandingOffer {
  const configured = landing.offers?.find(
    (offer) => offer.quantity === (landing.default_offer_quantity ?? 1),
  ) ?? landing.offers?.[0];

  if (configured) return configured;

  return {
    quantity: 1,
    label: "1 unidad",
    sublabel: null,
    discount_percent: 0,
    unit_price: landing.product_price,
    gross: landing.product_price,
    total: landing.product_price,
    savings: 0,
    compare_at_price: null,
  };
}

function item(landing: PublicLanding, quantity: number, value: number, currency: string) {
  return {
    // SKU is the catalog-stable commerce identifier Meta should match.
    item_id: landing.product_sku,
    item_name: landing.product_name,
    price: value / quantity,
    quantity,
    currency,
  };
}

function pushCommerceEvent(event: Record<string, unknown>) {
  const target = dataLayer();
  // Prevent GTM data-layer v2 recursive merging from carrying the previous
  // product or amount into a later commerce event.
  target.push({ ecommerce: null });
  target.push(event);
}

/** CTA activation: the existing GTM mapping emits Meta InitiateCheckout. */
export function trackInitiateCheckout(landing: PublicLanding, regional: RegionalSettings): void {
  const offer = offerForCheckout(landing);
  pushCommerceEvent({
    event: "begin_checkout",
    ecommerce: {
      currency: regional.currency,
      value: offer.total,
      items: [item(landing, offer.quantity, offer.total, regional.currency)],
    },
  });
}

/** Persisted COD order: GTM emits Meta Purchase via Pixel + CAPI. */
export function trackPurchase(
  landing: PublicLanding,
  purchase: PurchaseEventData,
  regional: RegionalSettings,
): void {
  const phone = toE164(regional, purchase.phone);
  const firstName = purchase.firstName.trim();
  const lastName = purchase.lastName.trim();
  const city = purchase.city.trim();
  const state = purchase.state.trim();

  pushCommerceEvent({
    event: "purchase",
    ecommerce: {
      transaction_id: String(purchase.orderId),
      currency: regional.currency,
      value: purchase.value,
      items: [item(landing, purchase.quantity, purchase.value, regional.currency)],
    },
    // Canonical fields feed the Meta tag's automatic data-layer mapping. The
    // billing aliases feed the User Data variables already present in the
    // supplied web container and are relayed by its Stape Data Tag.
    user_data: {
      phone,
      first_name: firstName,
      last_name: lastName,
      city,
      state,
      country: regional.countryCode.toLowerCase(),
      billing_phone: phone,
      billing_first_name: firstName,
      billing_last_name: lastName,
    },
  });
}
