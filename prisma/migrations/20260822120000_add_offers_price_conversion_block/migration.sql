-- Automatic one-to-three offer comparison block. Prices and discounts remain
-- owned by the Landing offer configuration; the block stores presentation-free
-- content and optional references to images already uploaded for the Landing.
ALTER TABLE "landing_blocks" DROP CONSTRAINT "landing_blocks_type_allowed";

ALTER TABLE "landing_blocks"
    ADD CONSTRAINT "landing_blocks_type_allowed" CHECK (
        "block_type" IN (
            'announcement_bar', 'cta', 'video_carousel',
            'cod_assurance', 'benefits', 'offer_price', 'offers_price',
            'included_benefits', 'reviews', 'faq', 'guarantee',
            'main_problem', 'solution_presentation', 'how_it_works',
            'audience', 'moment', 'price_summary', 'store_trust',
            'purchase_benefits', 'spacer'
        )
    );
