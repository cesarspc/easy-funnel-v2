import { beforeEach, describe, expect, it } from "vitest";
import type { PublicLanding } from "../api";
import { trackInitiateCheckout, trackPurchase } from "./metaCommerce";

const LANDING: PublicLanding = {
  landing_id: 7,
  product_id: 11,
  product_name: "Set de Sartenes",
  product_sku: "SET-001",
  product_price: 89900,
  slug: "set-sartenes",
  banners: [],
  cta_positions: [],
  cta_backgrounds: [],
  form_presentation: "modal",
  default_offer_quantity: 2,
  offers: [
    {
      quantity: 1,
      label: "1 unidad",
      sublabel: null,
      discount_percent: 0,
      unit_price: 89900,
      gross: 89900,
      total: 89900,
      savings: 0,
      compare_at_price: null,
    },
    {
      quantity: 2,
      label: "2 unidades",
      sublabel: null,
      discount_percent: 10,
      unit_price: 89900,
      gross: 179800,
      total: 161820,
      savings: 17980,
      compare_at_price: null,
    },
  ],
};

describe("Meta commerce dataLayer contract", () => {
  beforeEach(() => {
    window.dataLayer = [];
  });

  it("pushes the configured default offer as begin_checkout", () => {
    trackInitiateCheckout(LANDING);

    expect(window.dataLayer).toEqual([
      { ecommerce: null },
      {
        event: "begin_checkout",
        ecommerce: {
          currency: "COP",
          value: 161820,
          items: [
            {
              item_id: "SET-001",
              item_name: "Set de Sartenes",
              price: 80910,
              quantity: 2,
              currency: "COP",
            },
          ],
        },
      },
    ]);
  });

  it("pushes an authoritative purchase value and normalized matching data", () => {
    trackPurchase(LANDING, {
      orderId: 42,
      quantity: 2,
      value: 159800,
      firstName: " Ana María ",
      lastName: " Gómez ",
      phone: "+57 300 123 4567",
      city: " Medellín ",
      state: " Antioquia ",
    });

    expect(window.dataLayer?.[1]).toEqual({
      event: "purchase",
      ecommerce: {
        transaction_id: "42",
        currency: "COP",
        value: 159800,
        items: [
          {
            item_id: "SET-001",
            item_name: "Set de Sartenes",
            price: 79900,
            quantity: 2,
            currency: "COP",
          },
        ],
      },
      user_data: {
        phone: "+573001234567",
        first_name: "Ana María",
        last_name: "Gómez",
        city: "Medellín",
        state: "Antioquia",
        country: "co",
        billing_phone: "+573001234567",
        billing_first_name: "Ana María",
        billing_last_name: "Gómez",
      },
    });
  });
});
