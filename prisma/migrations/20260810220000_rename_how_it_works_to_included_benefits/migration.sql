-- Renames the `how_it_works` block type to `included_benefits` across the
-- conversion component vocabulary. The new name better describes the component's
-- evolved purpose: a list of included items/benefits with optional value and tag,
-- rather than a fixed three-step explainer.

-- Drop the old CHECK constraint first so the UPDATE can proceed.
ALTER TABLE "landing_blocks" DROP CONSTRAINT "landing_blocks_type_allowed";

-- Update existing rows.
UPDATE "landing_blocks" SET "block_type" = 'included_benefits' WHERE "block_type" = 'how_it_works';

-- Add the new CHECK constraint with the updated vocabulary.
ALTER TABLE "landing_blocks"
    ADD CONSTRAINT "landing_blocks_type_allowed" CHECK (
        "block_type" IN (
            'cod_assurance',
            'benefits',
            'offer_price',
            'included_benefits',
            'reviews',
            'faq',
            'guarantee',
            'announcement_bar'
        )
    );
