-- Add modular versions of the three visual sections inside the legacy
-- `offer_price` block, plus one fixed standard spacer. Existing rows remain
-- untouched so deployed landings preserve their exact rendering.
ALTER TABLE "landing_blocks"
    ADD CONSTRAINT "landing_blocks_type_allowed_v2" CHECK (
        "block_type" IN (
            'cod_assurance', 'benefits', 'offer_price', 'included_benefits',
            'reviews', 'faq', 'guarantee', 'announcement_bar', 'main_problem',
            'solution_presentation', 'how_it_works', 'audience', 'moment',
            'cta', 'video_carousel', 'price_summary', 'store_trust',
            'purchase_benefits', 'spacer'
        )
    );

-- Keep the old constraint active while PostgreSQL validates the additive
-- superset, then swap names. There is no interval with an unguarded column.
ALTER TABLE "landing_blocks" DROP CONSTRAINT "landing_blocks_type_allowed";
ALTER TABLE "landing_blocks"
    RENAME CONSTRAINT "landing_blocks_type_allowed_v2" TO "landing_blocks_type_allowed";
