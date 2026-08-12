-- Reusable Landing configuration snapshots ("templates").
--
-- One merchant sells across unrelated niches, and a funnel that converts is
-- mostly configuration: where the CTA repeats, what it says, how the COD form
-- presents its offers, which accent carries the page, and which conversion
-- components sit between which elements. A template stores exactly that, by
-- name, so the next product starts from a funnel that already works.
--
-- Images are deliberately excluded. Banners are the per-product part of a
-- landing, and they are also what the stored CTA positions and block slot
-- indices are indices *into*: the public page renders banners with CTA bands
-- interleaved, so the same slot_index addresses a different place in a
-- sequence of a different length. `banner_count` records the source landing's
-- banner count and the application refuses to load a template onto a landing
-- with a different one, rather than silently relocating components.
--
-- `config` carries the landing columns a template describes; `blocks` carries
-- the placed conversion components. Neither carries slug, product, or
-- publication status: those identify a landing, they do not configure it.

CREATE TABLE "landing_templates" (
    "id" BIGSERIAL NOT NULL,
    "name" TEXT NOT NULL,
    "banner_count" INTEGER NOT NULL,
    "config" JSONB NOT NULL,
    "blocks" JSONB NOT NULL DEFAULT '[]',
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL,

    CONSTRAINT "landing_templates_pkey" PRIMARY KEY ("id")
);

-- Names are the merchant's handle on a template and are unique so that
-- re-saving an existing name updates it in place instead of accumulating
-- several near-identical entries in the load dialog.
CREATE UNIQUE INDEX "idx_landing_templates_name" ON "landing_templates"("name");

-- Backstops for the application-level validation in
-- app/domains/landings/templates.py. The domain module is the primary
-- enforcement; keep the bounds in both places in sync.
ALTER TABLE "landing_templates"
    ADD CONSTRAINT "landing_templates_name_length" CHECK (
        char_length("name") BETWEEN 1 AND 80
    );

-- A landing carries at most 15 banners (Requirement 3.6), so a template
-- snapshotted from one can never legitimately require more.
ALTER TABLE "landing_templates"
    ADD CONSTRAINT "landing_templates_banner_count_range" CHECK (
        "banner_count" >= 0 AND "banner_count" <= 15
    );

-- `blocks` is a JSON array of placed components, never an object or scalar.
ALTER TABLE "landing_templates"
    ADD CONSTRAINT "landing_templates_blocks_is_array" CHECK (
        jsonb_typeof("blocks") = 'array'
    );

ALTER TABLE "landing_templates"
    ADD CONSTRAINT "landing_templates_config_is_object" CHECK (
        jsonb_typeof("config") = 'object'
    );
