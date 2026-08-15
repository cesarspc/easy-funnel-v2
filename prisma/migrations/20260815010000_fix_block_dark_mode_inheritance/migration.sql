-- Older validation normalized a missing per-block dark-mode override to
-- false. That made every untouched component force light mode instead of
-- inheriting landings.blocks_dark_mode. Remove only those generated false
-- values so existing components regain the landing default; explicit dark
-- overrides (true) remain intact. Because old generated and explicit false
-- values were indistinguishable, an old explicit light choice must be selected
-- again after this one-time repair. Future choices remain distinguishable from
-- the inherited null value through the tri-state validator.

UPDATE "landing_blocks"
SET "config" = "config" - 'dark_mode'
WHERE "config" ->> 'dark_mode' = 'false';
