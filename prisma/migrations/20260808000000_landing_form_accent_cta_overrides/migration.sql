-- AlterTable: separate form accent color from the CTA accent, and allow a
-- per-CTA-position text override.

ALTER TABLE "landings" ADD COLUMN "form_accent_color" VARCHAR(7);
ALTER TABLE "landings" ADD COLUMN "cta_text_overrides" JSONB NOT NULL DEFAULT '{}';

-- Same hex format guard as accent_color; null is allowed ("use accent_color").
ALTER TABLE "landings" ADD CONSTRAINT "landings_form_accent_color_format" CHECK (
    "form_accent_color" IS NULL OR "form_accent_color" ~ '^#[0-9a-f]{6}$'
);
