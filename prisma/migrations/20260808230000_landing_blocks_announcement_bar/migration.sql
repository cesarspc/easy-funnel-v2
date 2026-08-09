-- Adds `announcement_bar` to the conversion component vocabulary: a
-- top-of-page bar (single line of text + its own accent/background color),
-- placed and edited exactly like the other seven component types
-- (app/domains/landings/blocks.py). No new columns: `config` (jsonb) already
-- carries arbitrary content, and every block type as of this migration also
-- accepts an optional `accent_color` inside that same jsonb column.

ALTER TABLE "landing_blocks" DROP CONSTRAINT "landing_blocks_type_allowed";

ALTER TABLE "landing_blocks"
    ADD CONSTRAINT "landing_blocks_type_allowed" CHECK (
        "block_type" IN (
            'cod_assurance',
            'benefits',
            'offer_price',
            'how_it_works',
            'reviews',
            'faq',
            'guarantee',
            'announcement_bar'
        )
    );
