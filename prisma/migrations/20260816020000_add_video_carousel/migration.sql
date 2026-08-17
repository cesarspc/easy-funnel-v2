ALTER TABLE "landing_blocks" DROP CONSTRAINT "landing_blocks_type_allowed";

ALTER TABLE "landing_blocks"
    ADD CONSTRAINT "landing_blocks_type_allowed" CHECK (
        "block_type" IN (
            'cod_assurance', 'benefits', 'offer_price', 'included_benefits',
            'reviews', 'faq', 'guarantee', 'announcement_bar', 'main_problem',
            'solution_presentation', 'how_it_works', 'audience', 'moment',
            'cta', 'video_carousel'
        )
    );

CREATE TABLE "video_assets" (
    "id" BIGSERIAL PRIMARY KEY,
    "landing_block_id" BIGINT NOT NULL,
    "opaque_key" TEXT NOT NULL,
    "video_object_key" TEXT NOT NULL,
    "poster_object_key" TEXT NOT NULL,
    "width" INTEGER NOT NULL,
    "height" INTEGER NOT NULL,
    "duration_ms" INTEGER NOT NULL,
    "byte_size" BIGINT NOT NULL,
    "order_index" INTEGER NOT NULL,
    "caption" VARCHAR(100),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "video_assets_metrics_valid" CHECK (
        "width" > 0 AND "height" > 0 AND "duration_ms" > 0 AND
        "byte_size" > 0 AND "order_index" BETWEEN 0 AND 5
    ),
    CONSTRAINT "video_assets_landing_block_id_fkey" FOREIGN KEY ("landing_block_id")
        REFERENCES "landing_blocks"("id") ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE UNIQUE INDEX "video_assets_opaque_key_key" ON "video_assets"("opaque_key");
CREATE UNIQUE INDEX "idx_video_assets_block_order"
    ON "video_assets"("landing_block_id", "order_index");
CREATE INDEX "idx_video_assets_render"
    ON "video_assets"("landing_block_id", "order_index");
