-- AlterTable: add optional CTA text and animation to landings
ALTER TABLE "landings" ADD COLUMN "cta_text" VARCHAR(60);
ALTER TABLE "landings" ADD COLUMN "cta_animation" VARCHAR(10);

-- Constrain animation to allowed values
ALTER TABLE "landings" ADD CONSTRAINT "landings_cta_animation_check"
  CHECK ("cta_animation" IS NULL OR "cta_animation" IN ('slide', 'shake'));
