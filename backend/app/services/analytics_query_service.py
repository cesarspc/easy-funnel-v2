"""AnalyticsQueryService: per-day and per-landing aggregation (Requirement 8.11-8.13, 8.21).

Aggregation happens in the database, not in Python:

- orders per calendar day and per-day flagged counts use one grouped SQL
  statement each (day truncation has no Prisma Client equivalent);
- per-landing views and clicks share one bounded daily-traffic query, while
  orders use one grouped query, so the cost is constant in the number of
  landings rather than three queries per landing.

Both rate calculations delegate to `app.domains.analytics.rates`, which owns
the zero-guarded denominators (Requirement 8.21).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from prisma import Prisma
from upstash_redis import AsyncRedis

from app.db.repositories import LandingRepository
from app.domains.analytics.date_range import DateRange
from app.domains.analytics.models import (
    FraudAnalytics,
    LandingAnalytics,
    OrdersPerDay,
)
from app.domains.analytics.rates import conversion_rate, flagged_fraud_rate
from app.services.landing_traffic_service import LandingTrafficService

FLAGGED_ORDER_STATUS = "flagged_fraud"
_TRAFFIC_RECONCILE_TIMEOUT_SECONDS = 2.0
_TRAFFIC_RECONCILE_CONCURRENCY = 16
_logger = logging.getLogger("app.analytics.query")

# `query_raw` sends parameters as text, so the timestamp bounds are cast
# explicitly; without the cast PostgreSQL rejects `timestamptz >= text`.
_ORDERS_PER_DAY_SQL = """
    SELECT DATE("created_at" AT TIME ZONE 'America/Bogota') AS day, COUNT(*) AS count
    FROM "orders"
    WHERE "created_at" >= $1::timestamptz AND "created_at" <= $2::timestamptz
    GROUP BY DATE("created_at" AT TIME ZONE 'America/Bogota')
    ORDER BY day DESC
"""

_FRAUD_PER_DAY_SQL = """
    SELECT DATE("created_at" AT TIME ZONE 'America/Bogota') AS day,
           COUNT(*) AS total_orders,
           COUNT(*) FILTER (WHERE "status" = $3) AS flagged_orders
    FROM "orders"
    WHERE "created_at" >= $1::timestamptz AND "created_at" <= $2::timestamptz
    GROUP BY DATE("created_at" AT TIME ZONE 'America/Bogota')
    ORDER BY day DESC
"""

_LANDING_TRAFFIC_SQL = """
    SELECT "landing_id",
           SUM("view_count") AS views,
           SUM("cta_click_count") AS clicks
    FROM (
        SELECT "landing_id",
               "view_count" + "fallback_view_count" AS "view_count",
               "cta_click_count" + "fallback_cta_click_count" AS "cta_click_count"
        FROM "landing_analytics_daily"
        WHERE "event_date" BETWEEN $1::date AND $2::date

        UNION ALL

        SELECT "landing_id", COUNT(*)::bigint AS "view_count", 0::bigint AS "cta_click_count"
        FROM "landing_views"
        WHERE "created_at" >= $3::timestamptz AND "created_at" <= $4::timestamptz
        GROUP BY "landing_id"

        UNION ALL

        SELECT "landing_id", 0::bigint AS "view_count", COUNT(*)::bigint AS "cta_click_count"
        FROM "cta_clicks"
        WHERE "created_at" >= $3::timestamptz AND "created_at" <= $4::timestamptz
        GROUP BY "landing_id"
    ) AS traffic
    GROUP BY "landing_id"
"""


def _to_date(value: object) -> date:
    """Coerce a `DATE(...)` column value to `datetime.date`.

    The query engine returns the column as an ISO string; accepting a real
    `date` too keeps the service independent of that serialization detail.
    """
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _counts_by_landing(rows: list[dict]) -> dict[int, int]:
    """Map a Prisma `group_by(["landingId"], count=True)` result to {id: count}.

    Grouped BigInt keys come back as strings, so they are normalized to `int`
    to match the landing ids callers compare against.
    """
    counts: dict[int, int] = {}
    for row in rows:
        landing_id = row.get("landingId")
        if landing_id is None:
            continue
        count = row.get("_count") or {}
        counts[int(landing_id)] = int(count.get("_all", 0))
    return counts


def _traffic_by_landing(rows: list[dict]) -> tuple[dict[int, int], dict[int, int]]:
    """Map aggregated daily traffic rows to separate view and click totals."""
    views: dict[int, int] = {}
    clicks: dict[int, int] = {}
    for row in rows:
        landing_id = row.get("landing_id")
        if landing_id is None:
            continue
        normalized_id = int(landing_id)
        views[normalized_id] = int(row.get("views") or 0)
        clicks[normalized_id] = int(row.get("clicks") or 0)
    return views, clicks


async def _reconcile_traffic_with_deadline(
    traffic: LandingTrafficService,
    landing_ids: list[int],
) -> None:
    """Best-effort Redis reconciliation that can never hold the dashboard open."""
    semaphore = asyncio.Semaphore(_TRAFFIC_RECONCILE_CONCURRENCY)

    async def reconcile_one(landing_id: int) -> None:
        async with semaphore:
            await traffic.reconcile_landing(landing_id)

    try:
        await asyncio.wait_for(
            asyncio.gather(*(reconcile_one(landing_id) for landing_id in landing_ids)),
            timeout=_TRAFFIC_RECONCILE_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        _logger.warning(
            "Landing traffic reconciliation exceeded %.1fs; using durable snapshots.",
            _TRAFFIC_RECONCILE_TIMEOUT_SECONDS,
        )


class AnalyticsQueryService:
    """Service for analytics queries over orders, views, clicks."""

    def __init__(self, db: Prisma, redis: AsyncRedis | None = None) -> None:
        self._db = db
        self._traffic = LandingTrafficService(db, redis) if redis is not None else None

    async def get_orders_per_day(self, date_range: DateRange) -> list[OrdersPerDay]:
        """Return orders per calendar day within the inclusive range, newest first."""
        rows = await self._db.query_raw(_ORDERS_PER_DAY_SQL, date_range.start, date_range.end)
        return [OrdersPerDay(date=_to_date(row["day"]), count=int(row["count"])) for row in rows]

    async def get_landing_analytics(
        self, date_range: DateRange, *, landing_id: int | None = None
    ) -> list[LandingAnalytics]:
        """Return per-landing views, clicks, orders, and conversion rate.

        Covers every landing when `landing_id` is omitted, including landings
        with no activity in the range (reported as zeros), so the dashboard can
        show a complete per-landing table.
        """
        landings = LandingRepository(self._db)
        if landing_id is not None:
            landing = await landings.get_by_id(landing_id)
            selected = [landing] if landing is not None else []
        else:
            selected = await landings.list_all()

        if not selected:
            return []

        landing_ids = [landing.id for landing in selected]
        if self._traffic is not None:
            # Persist current live snapshots before reading PostgreSQL. Redis
            # failures are fail-open inside the traffic service, leaving the
            # last durable snapshot available to the dashboard.
            await _reconcile_traffic_with_deadline(self._traffic, landing_ids)
        views, clicks = _traffic_by_landing(
            await self._db.query_raw(
                _LANDING_TRAFFIC_SQL,
                date_range.start.date().isoformat(),
                date_range.end.date().isoformat(),
                date_range.start,
                date_range.end,
            )
        )
        window = {"createdAt": {"gte": date_range.start, "lte": date_range.end}}
        scope = {**window, "landingId": {"in": landing_ids}}
        orders = _counts_by_landing(
            await self._db.order.group_by(["landingId"], where=scope, count=True)
        )

        return [
            LandingAnalytics(
                landing_id=landing.id,
                views=views.get(landing.id, 0),
                clicks=clicks.get(landing.id, 0),
                orders=orders.get(landing.id, 0),
                conversion_rate=conversion_rate(
                    orders=orders.get(landing.id, 0), views=views.get(landing.id, 0)
                ),
            )
            for landing in selected
        ]

    async def get_fraud_analytics(self, date_range: DateRange) -> list[FraudAnalytics]:
        """Return per-day flagged-order counts and flagged-fraud rate, newest first.

        Counts distinct Flagged_Orders (orders persisted with `flagged_fraud`
        status), not `fraud_flags` rows: an order carrying several flags is one
        flagged order, so the rate can never exceed 1 (Requirement 8.13).
        """
        rows = await self._db.query_raw(
            _FRAUD_PER_DAY_SQL, date_range.start, date_range.end, FLAGGED_ORDER_STATUS
        )
        analytics: list[FraudAnalytics] = []
        for row in rows:
            total_orders = int(row["total_orders"])
            flagged_orders = int(row["flagged_orders"])
            analytics.append(
                FraudAnalytics(
                    date=_to_date(row["day"]),
                    flagged_orders=flagged_orders,
                    total_orders=total_orders,
                    flagged_fraud_rate=flagged_fraud_rate(
                        flagged_orders=flagged_orders, total_orders=total_orders
                    ),
                )
            )
        return analytics
