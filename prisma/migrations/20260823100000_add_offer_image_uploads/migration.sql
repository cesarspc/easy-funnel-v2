-- Dedicated, per-quantity images for the offers_price conversion block.
-- Images are relations rather than block config, so templates cannot copy
-- them to another Landing. Public outputs are fixed 500x500 WebPs.
CREATE TABLE "offer_image_assets" (
    "id" BIGSERIAL NOT NULL,
    "landing_block_id" BIGINT NOT NULL,
    "quantity" INTEGER NOT NULL,
    "opaque_key" TEXT NOT NULL,
    "source_object_key" TEXT NOT NULL,
    "image_object_key" TEXT NOT NULL,
    "width" INTEGER NOT NULL DEFAULT 500,
    "height" INTEGER NOT NULL DEFAULT 500,
    "byte_size" BIGINT NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL,

    CONSTRAINT "offer_image_assets_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "offer_image_assets_quantity_range" CHECK ("quantity" BETWEEN 1 AND 3),
    CONSTRAINT "offer_image_assets_fixed_size" CHECK ("width" = 500 AND "height" = 500),
    CONSTRAINT "offer_image_assets_landing_block_id_fkey"
        FOREIGN KEY ("landing_block_id") REFERENCES "landing_blocks"("id")
        ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE UNIQUE INDEX "offer_image_assets_opaque_key_key"
    ON "offer_image_assets"("opaque_key");
CREATE UNIQUE INDEX "idx_offer_images_block_quantity"
    ON "offer_image_assets"("landing_block_id", "quantity");
CREATE INDEX "idx_offer_images_render"
    ON "offer_image_assets"("landing_block_id", "quantity");
