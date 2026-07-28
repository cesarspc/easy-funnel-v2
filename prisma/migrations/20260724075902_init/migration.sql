-- CreateTable
CREATE TABLE "products" (
    "id" BIGSERIAL NOT NULL,
    "name" TEXT NOT NULL,
    "sku" TEXT NOT NULL,
    "price" DECIMAL(12,2) NOT NULL,
    "description" TEXT NOT NULL DEFAULT '',
    "status" TEXT NOT NULL DEFAULT 'paused',
    "retired_at" TIMESTAMPTZ,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL,

    CONSTRAINT "products_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "landings" (
    "id" BIGSERIAL NOT NULL,
    "product_id" BIGINT NOT NULL,
    "slug" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'draft',
    "cta_mode" TEXT NOT NULL,
    "cta_interval" INTEGER,
    "cta_positions" INTEGER[],
    "form_presentation" TEXT NOT NULL,
    "retired_at" TIMESTAMPTZ,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL,

    CONSTRAINT "landings_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "banners" (
    "id" BIGSERIAL NOT NULL,
    "landing_id" BIGINT NOT NULL,
    "order_index" INTEGER NOT NULL,
    "alt_text" TEXT NOT NULL,
    "image_asset_id" BIGINT NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL,

    CONSTRAINT "banners_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "image_assets" (
    "id" BIGSERIAL NOT NULL,
    "opaque_key" TEXT NOT NULL,
    "source_object_key" TEXT NOT NULL,
    "source_width" INTEGER NOT NULL,
    "source_height" INTEGER NOT NULL,
    "source_format" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'in_progress',
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "image_assets_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "image_variants" (
    "id" BIGSERIAL NOT NULL,
    "image_asset_id" BIGINT NOT NULL,
    "width" INTEGER NOT NULL,
    "format" TEXT NOT NULL,
    "height" INTEGER NOT NULL,
    "object_key" TEXT NOT NULL,
    "version" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "image_variants_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "orders" (
    "id" BIGSERIAL NOT NULL,
    "product_id" BIGINT NOT NULL,
    "landing_id" BIGINT NOT NULL,
    "landing_slug" TEXT NOT NULL,
    "customer_name" TEXT NOT NULL,
    "phone_e164" TEXT NOT NULL,
    "phone_normalized_key" TEXT NOT NULL,
    "department" TEXT NOT NULL,
    "city" TEXT NOT NULL,
    "address" TEXT NOT NULL,
    "quantity" INTEGER NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'pending',
    "ip_address" TEXT NOT NULL,
    "user_agent" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL,

    CONSTRAINT "orders_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "fraud_flags" (
    "id" BIGSERIAL NOT NULL,
    "order_id" BIGINT NOT NULL,
    "flag_type" TEXT NOT NULL,
    "detail" JSONB NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "fraud_flags_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "fraud_config" (
    "id" INTEGER NOT NULL DEFAULT 1,
    "duplicate_window_hours" INTEGER NOT NULL DEFAULT 24,
    "duplicate_match_fields" TEXT[] DEFAULT ARRAY['phone', 'ip']::TEXT[],
    "rate_limit_max" INTEGER NOT NULL DEFAULT 5,
    "rate_limit_window_minutes" INTEGER NOT NULL DEFAULT 10,
    "updated_at" TIMESTAMPTZ NOT NULL,

    CONSTRAINT "fraud_config_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "blacklist_entries" (
    "id" BIGSERIAL NOT NULL,
    "entry_type" TEXT NOT NULL,
    "value_normalized" TEXT NOT NULL,
    "reason" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "blacklist_entries_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "geoip_rules" (
    "id" BIGSERIAL NOT NULL,
    "location_code" TEXT NOT NULL,
    "action" TEXT NOT NULL,
    "enabled" BOOLEAN NOT NULL DEFAULT true,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL,

    CONSTRAINT "geoip_rules_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "landing_views" (
    "id" BIGSERIAL NOT NULL,
    "landing_id" BIGINT NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "landing_views_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "cta_clicks" (
    "id" BIGSERIAL NOT NULL,
    "landing_id" BIGINT NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "cta_clicks_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "admin_users" (
    "id" BIGSERIAL NOT NULL,
    "username" TEXT NOT NULL,
    "password_hash" TEXT NOT NULL,
    "role" TEXT NOT NULL DEFAULT 'admin',
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL,

    CONSTRAINT "admin_users_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "audit_log" (
    "id" BIGSERIAL NOT NULL,
    "actor" TEXT NOT NULL,
    "action" TEXT NOT NULL,
    "target_type" TEXT,
    "target_id" TEXT,
    "result" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "audit_log_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "idx_products_sku" ON "products"("sku");

-- CreateIndex
CREATE UNIQUE INDEX "landings_product_id_key" ON "landings"("product_id");

-- CreateIndex
CREATE UNIQUE INDEX "landings_slug_key" ON "landings"("slug");

-- CreateIndex
CREATE INDEX "idx_landings_slug" ON "landings"("slug");

-- CreateIndex
CREATE UNIQUE INDEX "idx_banners_landing_order" ON "banners"("landing_id", "order_index");

-- CreateIndex
CREATE UNIQUE INDEX "image_assets_opaque_key_key" ON "image_assets"("opaque_key");

-- CreateIndex
CREATE INDEX "idx_image_assets_opaque" ON "image_assets"("opaque_key");

-- CreateIndex
CREATE UNIQUE INDEX "idx_variants_asset" ON "image_variants"("image_asset_id", "width", "format");

-- CreateIndex
CREATE INDEX "idx_orders_status_created" ON "orders"("status", "created_at");

-- CreateIndex
CREATE INDEX "idx_orders_product_landing_created" ON "orders"("product_id", "landing_id", "created_at");

-- CreateIndex
CREATE INDEX "idx_orders_created" ON "orders"("created_at");

-- CreateIndex
CREATE INDEX "idx_orders_dupe" ON "orders"("phone_normalized_key", "ip_address", "created_at");

-- CreateIndex
CREATE INDEX "idx_fraud_flags_order" ON "fraud_flags"("order_id");

-- CreateIndex
CREATE UNIQUE INDEX "idx_blacklist_lookup" ON "blacklist_entries"("entry_type", "value_normalized");

-- CreateIndex
CREATE UNIQUE INDEX "geoip_rules_location_code_key" ON "geoip_rules"("location_code");

-- CreateIndex
CREATE INDEX "idx_geoip_rules_enabled" ON "geoip_rules"("enabled", "location_code");

-- CreateIndex
CREATE INDEX "idx_landing_views_landing_created" ON "landing_views"("landing_id", "created_at");

-- CreateIndex
CREATE INDEX "idx_cta_clicks_landing_created" ON "cta_clicks"("landing_id", "created_at");

-- CreateIndex
CREATE UNIQUE INDEX "admin_users_username_key" ON "admin_users"("username");

-- CreateIndex
CREATE INDEX "idx_audit_created" ON "audit_log"("created_at");

-- AddForeignKey
ALTER TABLE "landings" ADD CONSTRAINT "landings_product_id_fkey" FOREIGN KEY ("product_id") REFERENCES "products"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "banners" ADD CONSTRAINT "banners_landing_id_fkey" FOREIGN KEY ("landing_id") REFERENCES "landings"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "banners" ADD CONSTRAINT "banners_image_asset_id_fkey" FOREIGN KEY ("image_asset_id") REFERENCES "image_assets"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "image_variants" ADD CONSTRAINT "image_variants_image_asset_id_fkey" FOREIGN KEY ("image_asset_id") REFERENCES "image_assets"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "orders" ADD CONSTRAINT "orders_product_id_fkey" FOREIGN KEY ("product_id") REFERENCES "products"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "orders" ADD CONSTRAINT "orders_landing_id_fkey" FOREIGN KEY ("landing_id") REFERENCES "landings"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "fraud_flags" ADD CONSTRAINT "fraud_flags_order_id_fkey" FOREIGN KEY ("order_id") REFERENCES "orders"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

-- AddForeignKey
ALTER TABLE "landing_views" ADD CONSTRAINT "landing_views_landing_id_fkey" FOREIGN KEY ("landing_id") REFERENCES "landings"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "cta_clicks" ADD CONSTRAINT "cta_clicks_landing_id_fkey" FOREIGN KEY ("landing_id") REFERENCES "landings"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- CheckConstraint: products
ALTER TABLE "products" ADD CONSTRAINT "products_name_length" CHECK (char_length(btrim("name")) BETWEEN 1 AND 160);
ALTER TABLE "products" ADD CONSTRAINT "products_price_range" CHECK ("price" >= 0.01 AND "price" <= 999999999.99);
ALTER TABLE "products" ADD CONSTRAINT "products_status_allowed" CHECK ("status" IN ('active','paused','retired'));

-- CheckConstraint: landings
ALTER TABLE "landings" ADD CONSTRAINT "landings_slug_format" CHECK ("slug" ~ '^[a-z0-9]+(-[a-z0-9]+)*$');
ALTER TABLE "landings" ADD CONSTRAINT "landings_status_allowed" CHECK ("status" IN ('draft','published'));
ALTER TABLE "landings" ADD CONSTRAINT "landings_cta_mode_allowed" CHECK ("cta_mode" IN ('after_every','every_n','fixed_positions'));
ALTER TABLE "landings" ADD CONSTRAINT "landings_cta_interval_range" CHECK ("cta_interval" IS NULL OR ("cta_interval" BETWEEN 1 AND 15));
ALTER TABLE "landings" ADD CONSTRAINT "landings_form_presentation_allowed" CHECK ("form_presentation" IN ('inline','modal'));

-- CheckConstraint: banners
ALTER TABLE "banners" ADD CONSTRAINT "banners_alt_text_length" CHECK (char_length(btrim("alt_text")) BETWEEN 1 AND 200);

-- CheckConstraint: image_assets
ALTER TABLE "image_assets" ADD CONSTRAINT "image_assets_source_width_range" CHECK ("source_width" BETWEEN 480 AND 8000);
ALTER TABLE "image_assets" ADD CONSTRAINT "image_assets_source_height_range" CHECK ("source_height" BETWEEN 1 AND 8000);
ALTER TABLE "image_assets" ADD CONSTRAINT "image_assets_total_pixels_range" CHECK (("source_width")::bigint * ("source_height")::bigint <= 40000000);
ALTER TABLE "image_assets" ADD CONSTRAINT "image_assets_source_format_allowed" CHECK ("source_format" IN ('jpeg','png','webp'));
ALTER TABLE "image_assets" ADD CONSTRAINT "image_assets_status_allowed" CHECK ("status" IN ('in_progress','complete'));

-- CheckConstraint: image_variants
ALTER TABLE "image_variants" ADD CONSTRAINT "image_variants_format_allowed" CHECK ("format" IN ('webp','jpeg'));

-- CheckConstraint: orders
ALTER TABLE "orders" ADD CONSTRAINT "orders_status_allowed" CHECK ("status" IN ('pending','confirmed','shipped','delivered','cancelled','flagged_fraud'));
ALTER TABLE "orders" ADD CONSTRAINT "orders_customer_name_length" CHECK (char_length(btrim("customer_name")) BETWEEN 2 AND 120);
ALTER TABLE "orders" ADD CONSTRAINT "orders_department_length" CHECK (char_length(btrim("department")) BETWEEN 2 AND 100);
ALTER TABLE "orders" ADD CONSTRAINT "orders_city_length" CHECK (char_length(btrim("city")) BETWEEN 2 AND 100);
ALTER TABLE "orders" ADD CONSTRAINT "orders_address_length" CHECK (char_length(btrim("address")) BETWEEN 5 AND 250);
ALTER TABLE "orders" ADD CONSTRAINT "orders_quantity_range" CHECK ("quantity" BETWEEN 1 AND 99);

-- CheckConstraint: fraud_flags
ALTER TABLE "fraud_flags" ADD CONSTRAINT "fraud_flags_type_allowed" CHECK ("flag_type" IN ('duplicate','blacklist','rate_limit_phone','rate_limit_ip','geoip'));

-- CheckConstraint: fraud_config (singleton + thresholds)
ALTER TABLE "fraud_config" ADD CONSTRAINT "fraud_config_singleton" CHECK ("id" = 1);
ALTER TABLE "fraud_config" ADD CONSTRAINT "fraud_config_duplicate_window_positive" CHECK ("duplicate_window_hours" > 0);
ALTER TABLE "fraud_config" ADD CONSTRAINT "fraud_config_match_fields_non_empty" CHECK (array_length("duplicate_match_fields", 1) > 0);
ALTER TABLE "fraud_config" ADD CONSTRAINT "fraud_config_rate_limit_max_positive" CHECK ("rate_limit_max" > 0);
ALTER TABLE "fraud_config" ADD CONSTRAINT "fraud_config_rate_limit_window_positive" CHECK ("rate_limit_window_minutes" > 0);

-- CheckConstraint: blacklist_entries
ALTER TABLE "blacklist_entries" ADD CONSTRAINT "blacklist_entries_type_allowed" CHECK ("entry_type" IN ('phone','ip'));
ALTER TABLE "blacklist_entries" ADD CONSTRAINT "blacklist_entries_reason_length" CHECK (char_length(btrim("reason")) BETWEEN 1 AND 500);

-- CheckConstraint: geoip_rules
ALTER TABLE "geoip_rules" ADD CONSTRAINT "geoip_rules_action_allowed" CHECK ("action" IN ('flag','block'));

-- Seed: fraud_config singleton row (defaults per design.md: 24h window, {phone,ip}, 5/10min)
INSERT INTO "fraud_config" ("id", "duplicate_window_hours", "duplicate_match_fields", "rate_limit_max", "rate_limit_window_minutes", "updated_at")
VALUES (1, 24, ARRAY['phone','ip']::TEXT[], 5, 10, CURRENT_TIMESTAMP)
ON CONFLICT ("id") DO NOTHING;
