-- Conversion components placed in a Landing's rendered sequence
-- (Requirement 3.27-3.31).
--
-- `slot_index` counts the rendered elements the block follows. The public page
-- renders up to 15 banners with CTA bands interleaved at `cta_positions`, so
-- the sequence is at most 30 elements long and slot 30 is "after everything";
-- the upper bound is a defense-in-depth backstop for the application check.
--
-- `config` is content only (jsonb). Presentation for each `block_type` is
-- fixed in the Landing chrome, so there is no column here for spacing, color,
-- or type: a merchant places a component and writes its copy, and cannot
-- de-optimize a component whose whole purpose is conversion.

CREATE TABLE "landing_blocks" (
    "id" BIGSERIAL NOT NULL,
    "landing_id" BIGINT NOT NULL,
    "block_type" TEXT NOT NULL,
    "slot_index" INTEGER NOT NULL,
    "order_index" INTEGER NOT NULL,
    "config" JSONB NOT NULL,
    "enabled" BOOLEAN NOT NULL DEFAULT true,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL,

    CONSTRAINT "landing_blocks_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "idx_landing_blocks_slot"
    ON "landing_blocks"("landing_id", "slot_index", "order_index");

CREATE INDEX "idx_landing_blocks_render"
    ON "landing_blocks"("landing_id", "slot_index", "order_index");

ALTER TABLE "landing_blocks"
    ADD CONSTRAINT "landing_blocks_landing_id_fkey"
    FOREIGN KEY ("landing_id") REFERENCES "landings"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE;

-- Enum/range backstops for the application-level validation in
-- app/domains/landings/blocks.py. Keep the allowlist in both places in sync:
-- the domain module is the primary enforcement, this is the database's.
ALTER TABLE "landing_blocks"
    ADD CONSTRAINT "landing_blocks_type_allowed" CHECK (
        "block_type" IN (
            'cod_assurance',
            'benefits',
            'offer_price',
            'how_it_works',
            'reviews',
            'faq',
            'guarantee'
        )
    );

ALTER TABLE "landing_blocks"
    ADD CONSTRAINT "landing_blocks_slot_range" CHECK (
        "slot_index" >= 0 AND "slot_index" <= 30
    );

ALTER TABLE "landing_blocks"
    ADD CONSTRAINT "landing_blocks_order_range" CHECK (
        "order_index" >= 0 AND "order_index" <= 9
    );
