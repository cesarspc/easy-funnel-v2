-- CreateTable
CREATE TABLE "landing_analytics_daily" (
    "id" BIGSERIAL NOT NULL,
    "landing_id" BIGINT NOT NULL,
    "event_date" DATE NOT NULL,
    "view_count" BIGINT NOT NULL DEFAULT 0,
    "cta_click_count" BIGINT NOT NULL DEFAULT 0,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "landing_analytics_daily_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "landing_analytics_daily_counts_nonnegative"
        CHECK ("view_count" >= 0 AND "cta_click_count" >= 0)
);

-- Historical rows intentionally remain in landing_views and cta_clicks. The
-- reporting query sums those immutable legacy events together with this table.
-- This avoids a backfill cutover race in which an old application instance
-- could write an event after a one-time copy but before the new release starts.

-- CreateIndex
CREATE UNIQUE INDEX "idx_landing_analytics_daily_unique"
ON "landing_analytics_daily"("landing_id", "event_date");

-- CreateIndex
CREATE INDEX "idx_landing_analytics_daily_range"
ON "landing_analytics_daily"("event_date", "landing_id");

-- AddForeignKey
ALTER TABLE "landing_analytics_daily"
ADD CONSTRAINT "landing_analytics_daily_landing_id_fkey"
FOREIGN KEY ("landing_id") REFERENCES "landings"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;
