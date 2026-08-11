-- Adds a landing-level default for dark mode on conversion blocks.
-- Individual blocks can still override via their own `dark_mode` config field.

ALTER TABLE "landings" ADD COLUMN "blocks_dark_mode" BOOLEAN NOT NULL DEFAULT false;
