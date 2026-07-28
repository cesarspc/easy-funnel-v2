-- Per-landing choice of how the CTA band between two banners is painted:
-- 'gradient' fades from the bottom edge of the banner above to the top edge of
-- the banner below; 'solid' fills the band with the midpoint of the two.
-- Existing landings default to 'gradient', which is what they already render.
ALTER TABLE "landings" ADD COLUMN     "cta_band_style" TEXT NOT NULL DEFAULT 'gradient';

ALTER TABLE "landings" ADD CONSTRAINT "landings_cta_band_style_allowed" CHECK ("cta_band_style" IN ('gradient','solid'));
