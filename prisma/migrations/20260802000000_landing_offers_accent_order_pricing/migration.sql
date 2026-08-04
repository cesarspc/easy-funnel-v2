-- Per-landing offer configuration, accent color, and the order money snapshot
-- the offer discounts make necessary.
--
-- Three things ship together because they are one feature: a merchant chooses
-- how many quantity offers the COD form shows, writes the copy and discount for
-- each, and picks the accent color the public page is painted with.

-- ---------------------------------------------------------------------------
-- Landing: accent color + offer configuration
-- ---------------------------------------------------------------------------

-- The one color a merchant controls on the public page. Every other shade the
-- chrome needs (hover, light tint behind the offer tiers, readable foreground)
-- is derived from this in app/domains/landings/accent_color.py, so a merchant
-- cannot pick a palette that fails contrast. The default is the green the
-- landing chrome already shipped, so existing landings render unchanged.
ALTER TABLE "landings" ADD COLUMN "accent_color" VARCHAR(7) NOT NULL DEFAULT '#1a7a4c';

ALTER TABLE "landings"
    ADD CONSTRAINT "landings_accent_color_format" CHECK (
        "accent_color" ~ '^#[0-9a-f]{6}$'
    );

-- How many quantity offers the COD form presents. Existing landings default to
-- 3, which is exactly the 1/2/3 tier list the form hardcoded before this.
ALTER TABLE "landings" ADD COLUMN "offer_count" INTEGER NOT NULL DEFAULT 3;

ALTER TABLE "landings"
    ADD CONSTRAINT "landings_offer_count_range" CHECK (
        "offer_count" >= 1 AND "offer_count" <= 3
    );

-- Per-offer copy and pricing (jsonb): one entry per quantity 1..offer_count,
-- each `{quantity, label, sublabel, discount_percent, compare_at_price}`.
-- Validated in app/domains/landings/offers.py; that module is the primary
-- enforcement and this column deliberately carries no per-key constraints
-- beyond being an array, since the shape is the domain's to own.
--
-- Empty array = "use the generated defaults", which is what every landing
-- created before this migration gets.
ALTER TABLE "landings" ADD COLUMN "offers" JSONB NOT NULL DEFAULT '[]';

ALTER TABLE "landings"
    ADD CONSTRAINT "landings_offers_is_array" CHECK (
        jsonb_typeof("offers") = 'array'
    );

-- ---------------------------------------------------------------------------
-- Order: money snapshot
-- ---------------------------------------------------------------------------

-- Offer discounts are merchant-editable at any time. Without a snapshot, the
-- amount a courier must collect for an order placed today would change the
-- moment the merchant edits the landing tomorrow. These columns record what was
-- actually agreed at submission.
--
-- Backfill is exact rather than a guess: before this migration no discount
-- mechanism existed, so every historical order was priced at the product's
-- current price with no reduction.
ALTER TABLE "orders" ADD COLUMN "unit_price" DECIMAL(12,2);
ALTER TABLE "orders" ADD COLUMN "discount_percent" INTEGER NOT NULL DEFAULT 0;
ALTER TABLE "orders" ADD COLUMN "total_price" DECIMAL(12,2);

UPDATE "orders" AS o
SET "unit_price" = p."price",
    "total_price" = ROUND(p."price" * o."quantity", 2)
FROM "products" AS p
WHERE p."id" = o."product_id"
  AND o."unit_price" IS NULL;

ALTER TABLE "orders" ALTER COLUMN "unit_price" SET NOT NULL;
ALTER TABLE "orders" ALTER COLUMN "total_price" SET NOT NULL;

ALTER TABLE "orders"
    ADD CONSTRAINT "orders_discount_percent_range" CHECK (
        "discount_percent" >= 0 AND "discount_percent" <= 90
    );

ALTER TABLE "orders"
    ADD CONSTRAINT "orders_unit_price_positive" CHECK ("unit_price" > 0);

ALTER TABLE "orders"
    ADD CONSTRAINT "orders_total_price_positive" CHECK ("total_price" > 0);
