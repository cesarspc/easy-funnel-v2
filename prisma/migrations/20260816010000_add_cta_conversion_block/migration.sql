-- Allow an additional purchase CTA to be ordered between conversion blocks.
ALTER TABLE "landing_blocks" DROP CONSTRAINT "landing_blocks_type_allowed";

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
            'announcement_bar',
            'main_problem',
            'solution_presentation',
            'how_it_works',
            'audience',
            'moment',
            'cta'
        )
    );
