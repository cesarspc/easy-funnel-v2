-- Additive MasterShop fulfillment integration.
-- Existing product/order columns and rows are intentionally untouched. No
-- sync rows are backfilled, preventing historical orders from being sent.

CREATE TABLE "order_fulfillment_details" (
    "order_id" BIGINT NOT NULL,
    "first_name" TEXT NOT NULL,
    "last_name" TEXT NOT NULL,
    "address1" TEXT NOT NULL,
    "address2" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "order_fulfillment_details_pkey" PRIMARY KEY ("order_id")
);

CREATE TABLE "mastershop_product_mappings" (
    "id" BIGSERIAL NOT NULL,
    "product_id" BIGINT NOT NULL,
    "selection_key" TEXT NOT NULL,
    "variant_selection" JSONB NOT NULL DEFAULT '{}'::jsonb,
    "mastershop_product_id" BIGINT NOT NULL,
    "mastershop_variant_id" BIGINT,
    "weight" DECIMAL(8,3) NOT NULL DEFAULT 1,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "mastershop_product_mappings_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "mastershop_order_syncs" (
    "id" BIGSERIAL NOT NULL,
    "order_id" BIGINT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'pending',
    "attempt_count" INTEGER NOT NULL DEFAULT 0,
    "request_body" JSONB,
    "response_status" INTEGER,
    "response_body" JSONB,
    "last_error" TEXT,
    "last_attempt_at" TIMESTAMPTZ,
    "synced_at" TIMESTAMPTZ,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "mastershop_order_syncs_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "idx_mastershop_product_mapping_selection"
ON "mastershop_product_mappings"("product_id", "selection_key");
CREATE INDEX "idx_mastershop_product_mapping_product"
ON "mastershop_product_mappings"("product_id");
CREATE UNIQUE INDEX "mastershop_order_syncs_order_id_key"
ON "mastershop_order_syncs"("order_id");
CREATE INDEX "idx_mastershop_order_sync_status"
ON "mastershop_order_syncs"("status", "updated_at");

ALTER TABLE "order_fulfillment_details"
ADD CONSTRAINT "order_fulfillment_details_order_id_fkey"
FOREIGN KEY ("order_id") REFERENCES "orders"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

ALTER TABLE "mastershop_product_mappings"
ADD CONSTRAINT "mastershop_product_mappings_product_id_fkey"
FOREIGN KEY ("product_id") REFERENCES "products"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

ALTER TABLE "mastershop_order_syncs"
ADD CONSTRAINT "mastershop_order_syncs_order_id_fkey"
FOREIGN KEY ("order_id") REFERENCES "orders"("id") ON DELETE RESTRICT ON UPDATE RESTRICT;

ALTER TABLE "mastershop_order_syncs"
ADD CONSTRAINT "mastershop_order_syncs_status_allowed"
CHECK ("status" IN ('pending', 'syncing', 'success', 'failed', 'waiting_review'));

ALTER TABLE "mastershop_order_syncs"
ADD CONSTRAINT "mastershop_order_syncs_attempt_count_nonnegative"
CHECK ("attempt_count" >= 0);

ALTER TABLE "mastershop_product_mappings"
ADD CONSTRAINT "mastershop_product_mapping_ids_positive"
CHECK ("mastershop_product_id" > 0 AND ("mastershop_variant_id" IS NULL OR "mastershop_variant_id" > 0));

ALTER TABLE "mastershop_product_mappings"
ADD CONSTRAINT "mastershop_product_mapping_weight_positive"
CHECK ("weight" > 0);
