ALTER TABLE "products"
ADD COLUMN "variant_options" JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE "landings"
ADD COLUMN "default_offer_quantity" INTEGER NOT NULL DEFAULT 1;

ALTER TABLE "orders"
ADD COLUMN "variant_selections" JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE "fraud_config"
ADD COLUMN "banned_cities" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];

ALTER TABLE "landings"
ADD CONSTRAINT "landings_default_offer_quantity_range"
CHECK ("default_offer_quantity" BETWEEN 1 AND 3);
