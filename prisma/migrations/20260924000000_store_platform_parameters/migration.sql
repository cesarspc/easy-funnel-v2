-- Market conventions and fulfillment integration become admin-editable store
-- settings instead of code constants / environment variables. Defaults keep
-- the existing Colombian behavior for upgraded databases. Fulfillment columns
-- stay NULL until the application seeds them once from the legacy
-- FULFILLMENT_PROVIDER / MASTERSHOP_* variables at startup.
ALTER TABLE "store_settings"
    ADD COLUMN "country_code" VARCHAR(2) NOT NULL DEFAULT 'CO',
    ADD COLUMN "locale" VARCHAR(35) NOT NULL DEFAULT 'es-CO',
    ADD COLUMN "currency" VARCHAR(3) NOT NULL DEFAULT 'COP',
    ADD COLUMN "time_zone" VARCHAR(64) NOT NULL DEFAULT 'America/Bogota',
    ADD COLUMN "phone_country_code" VARCHAR(4) NOT NULL DEFAULT '57',
    ADD COLUMN "phone_national_pattern" VARCHAR(100) NOT NULL DEFAULT '3[0-9]{9}',
    ADD COLUMN "fulfillment_provider" VARCHAR(20),
    ADD COLUMN "mastershop_orders_url" TEXT,
    ADD COLUMN "mastershop_timeout_seconds" DOUBLE PRECISION,
    ADD COLUMN "mastershop_api_key" TEXT,
    ADD CONSTRAINT "store_settings_country_code" CHECK ("country_code" ~ '^[A-Z]{2}$'),
    ADD CONSTRAINT "store_settings_currency" CHECK ("currency" ~ '^[A-Z]{3}$'),
    ADD CONSTRAINT "store_settings_phone_country_code" CHECK ("phone_country_code" ~ '^[1-9][0-9]{0,3}$'),
    ADD CONSTRAINT "store_settings_fulfillment_provider" CHECK ("fulfillment_provider" IS NULL OR "fulfillment_provider" IN ('none', 'mastershop')),
    ADD CONSTRAINT "store_settings_mastershop_timeout" CHECK ("mastershop_timeout_seconds" IS NULL OR ("mastershop_timeout_seconds" > 0 AND "mastershop_timeout_seconds" <= 30));
