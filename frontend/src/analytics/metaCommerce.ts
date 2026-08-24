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

const CURRENCY = "COP" as const;

interface DataLayerWindow extends Window {
  dataLayer?: Record<string, unknown>[];
}

export interface PurchaseCustomerData {
  firstName: string;
  lastName: string;
  phone: string;
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

function item(landing: PublicLanding, quantity: number, value: number) {
  return {
    // SKU is the catalog-stable commerce identifier Meta should match.
    item_id: landing.product_sku,
    item_name: landing.product_name,
    price: value / quantity,
    quantity,
    currency: CURRENCY,
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
export function trackInitiateCheckout(landing: PublicLanding): void {
  const offer = offerForCheckout(landing);
  pushCommerceEvent({
    event: "begin_checkout",
    ecommerce: {
      currency: CURRENCY,
      value: offer.total,
      items: [item(landing, offer.quantity, offer.total)],
    },
  });
}

/** Successful, non-fraud COD order: GTM emits Meta Purchase via Pixel + CAPI. */
export function trackPurchase(landing: PublicLanding, purchase: PurchaseEventData): void {
  const normalizedPhone = purchase.phone.replace(/\D/g, "").replace(/^57/, "");
  const phone = `+57${normalizedPhone}`;
  const firstName = purchase.firstName.trim();
  const lastName = purchase.lastName.trim();

  pushCommerceEvent({
    event: "purchase",
    ecommerce: {
      transaction_id: String(purchase.orderId),
      currency: CURRENCY,
      value: purchase.value,
      items: [item(landing, purchase.quantity, purchase.value)],
    },
    // Canonical fields feed the Meta tag's automatic data-layer mapping. The
    // billing aliases feed the User Data variables already present in the
    // supplied web container and are relayed by its Stape Data Tag.
    user_data: {
      phone,
      first_name: firstName,
      last_name: lastName,
      billing_phone: phone,
      billing_first_name: firstName,
      billing_last_name: lastName,
    },
  });
}
