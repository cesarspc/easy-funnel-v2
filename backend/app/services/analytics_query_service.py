"""AnalyticsQueryService: per-day and per-landing aggregation (Requirement 8.11-8.13, 8.21).

Aggregation happens in the database, not in Python:

- orders per calendar day and per-day flagged counts use one grouped SQL
  statement each (day truncation has no Prisma Client equivalent);
- per-landing views/clicks/orders use one grouped query per collection, so the
  cost is constant in the number of landings rather than three queries per
  landing.

Both rate calculations delegate to `app.domains.analytics.rates`, which owns
the zero-guarded denominators (Requirement 8.21).
"""

from __future__ import annotations

from datetime import date

from prisma import Prisma

from app.db.repositories import LandingRepository
from app.domains.analytics.date_range import DateRange
from app.domains.analytics.models import (
    FraudAnalytics,
    LandingAnalytics,
    OrdersPerDay,
)
from app.domains.analytics.rates import conversion_rate, flagged_fraud_rate

FLAGGED_ORDER_STATUS = "flagged_fraud"

# `query_raw` sends parameters as text, so the timestamp bounds are cast
# explicitly; without the cast PostgreSQL rejects `timestamptz >= text`.
_ORDERS_PER_DAY_SQL = """
    SELECT DATE("created_at") AS day, COUNT(*) AS count
    FROM "orders"
    WHERE "created_at" >= $1::timestamptz AND "created_at" <= $2::timestamptz
    GROUP BY DATE("created_at")
    ORDER BY day DESC
"""

_FRAUD_PER_DAY_SQL = """
    SELECT DATE("created_at") AS day,
           COUNT(*) AS total_orders,
           COUNT(*) FILTER (WHERE "status" = $3) AS flagged_orders
    FROM "orders"
    WHERE "created_at" >= $1::timestamptz AND "created_at" <= $2::timestamptz
    GROUP BY DATE("created_at")
    ORDER BY day DESC
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


class AnalyticsQueryService:
    """Service for analytics queries over orders, views, clicks."""

    def __init__(self, db: Prisma) -> None:
        self._db = db

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
        window = {"createdAt": {"gte": date_range.start, "lte": date_range.end}}
        scope = {**window, "landingId": {"in": landing_ids}}

        views = _counts_by_landing(
            await self._db.landingview.group_by(["landingId"], where=scope, count=True)
        )
        clicks = _counts_by_landing(
            await self._db.ctaclick.group_by(["landingId"], where=scope, count=True)
        )
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
