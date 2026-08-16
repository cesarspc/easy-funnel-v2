-- Redis snapshots are absolute and idempotent. Direct PostgreSQL increments
-- used during Redis outages live in separate columns so later snapshots can
-- never overwrite fallback traffic.
ALTER TABLE "landing_analytics_daily"
ADD COLUMN "fallback_view_count" BIGINT NOT NULL DEFAULT 0,
ADD COLUMN "fallback_cta_click_count" BIGINT NOT NULL DEFAULT 0;

ALTER TABLE "landing_analytics_daily"
ADD CONSTRAINT "landing_analytics_daily_fallback_counts_nonnegative"
CHECK ("fallback_view_count" >= 0 AND "fallback_cta_click_count" >= 0);
