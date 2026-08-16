-- Per-position CTA appearance overrides. Existing landings keep the automatic
-- banner-derived gradient/solid treatment through the empty-object default.
ALTER TABLE "landings"
ADD COLUMN "cta_color_modes" JSONB NOT NULL DEFAULT '{}';
