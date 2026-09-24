"""High-throughput Landing traffic counters backed by Redis and PostgreSQL.

The live request path performs one atomic Redis operation. Absolute Redis
snapshots are persisted idempotently when a merchant business day closes and whenever the
administrator reads Landing analytics. A historical Redis key receives its
48-hour TTL only after PostgreSQL acknowledges the snapshot.

No scheduler is required: active Landings reconcile on their next event and
inactive Landings reconcile when analytics is opened. Until then, their final
key has no expiry, so an idle Landing cannot lose its last day of traffic.
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from prisma import Prisma
from redis.asyncio import Redis as AsyncRedis

from app.core.regional import business_today
from app.db.repositories import CtaClickRepository, LandingViewRepository

_logger = logging.getLogger("app.analytics.traffic")

ACKNOWLEDGED_TTL_SECONDS = 48 * 60 * 60

# Both keys use the same Redis hash tag (`{landing_id}`), keeping the Lua
# operation cluster-safe while it increments the day hash and indexes the day.
_INCREMENT_SCRIPT = """
-- LANDING_TRAFFIC_INCREMENT
local count = redis.call("HINCRBY", KEYS[1], ARGV[2], 1)
redis.call("SADD", KEYS[2], ARGV[1])
local has_older_day = 0
for _, stored_day in ipairs(redis.call("SMEMBERS", KEYS[2])) do
  if stored_day < ARGV[1] then
    has_older_day = 1
    break
  end
end
return {count, has_older_day}
"""

_ACKNOWLEDGE_SCRIPT = """
-- LANDING_TRAFFIC_ACKNOWLEDGE
redis.call("EXPIRE", KEYS[1], ARGV[2])
redis.call("SREM", KEYS[2], ARGV[1])
return 1
"""


def _day_key(landing_id: int, event_date: str) -> str:
    return f"analytics:landing:{{{landing_id}}}:day:{event_date}"


def _days_key(landing_id: int) -> str:
    return f"analytics:landing:{{{landing_id}}}:days"


class LandingTrafficService:
    """Record and reconcile Landing views and CTA activations."""

    def __init__(self, db: Prisma, redis: AsyncRedis, *, time_zone: str) -> None:
        self._redis = redis
        self._time_zone = time_zone
        self._views = LandingViewRepository(db)
        self._clicks = CtaClickRepository(db)

    async def record_view(self, landing_id: int, *, now: datetime | None = None) -> None:
        await self._record(landing_id, field="views", now=now)

    async def record_cta_click(self, landing_id: int, *, now: datetime | None = None) -> None:
        await self._record(landing_id, field="cta_clicks", now=now)

    async def _record(self, landing_id: int, *, field: str, now: datetime | None) -> None:
        today = business_today(self._time_zone, now=now)
        today_iso = today.isoformat()
        try:
            result = await self._redis.eval(
                _INCREMENT_SCRIPT,
                keys=[_day_key(landing_id, today_iso), _days_key(landing_id)],
                args=[today_iso, field],
            )
        except Exception:
            _logger.warning(
                "Redis traffic increment unavailable; using PostgreSQL fallback.",
                exc_info=True,
            )
            if field == "views":
                await self._views.record_fallback(landing_id)
            else:
                await self._clicks.record_fallback(landing_id)
            return

        has_older_day = bool(int(result[1]))
        if has_older_day:
            # The current event is already safe in Redis. A reconciliation
            # failure must not turn a successful tracking request into a 5xx;
            # the unacknowledged key has no TTL and will be retried later.
            await self.reconcile_landing(landing_id, today=today, include_current=False)

    async def reconcile_landing(
        self,
        landing_id: int,
        *,
        today: date | None = None,
        include_current: bool = True,
    ) -> bool:
        """Persist pending snapshots; return false when Redis/DB was unavailable."""
        current_day = today or business_today(self._time_zone)
        try:
            raw_days = await self._redis.smembers(_days_key(landing_id))
        except Exception:
            _logger.warning("Could not read pending Landing traffic from Redis.", exc_info=True)
            return False

        succeeded = True
        for raw_day in sorted(str(value) for value in raw_days):
            try:
                event_day = date.fromisoformat(raw_day)
            except ValueError:
                _logger.error("Ignoring invalid internal traffic day: %r", raw_day)
                continue
            if not include_current and event_day >= current_day:
                continue

            day_key = _day_key(landing_id, raw_day)
            try:
                snapshot = await self._redis.hgetall(day_key)
                if not snapshot:
                    # A previously acknowledged key may have expired while a
                    # stale index member survived an interrupted acknowledgement.
                    await self._redis.srem(_days_key(landing_id), raw_day)
                    continue
                views = int(snapshot.get("views", 0))
                clicks = int(snapshot.get("cta_clicks", 0))
                await self._views.persist_redis_snapshot(
                    landing_id,
                    event_date=raw_day,
                    views=views,
                    cta_clicks=clicks,
                )
                if event_day < current_day:
                    await self._redis.eval(
                        _ACKNOWLEDGE_SCRIPT,
                        keys=[day_key, _days_key(landing_id)],
                        args=[raw_day, str(ACKNOWLEDGED_TTL_SECONDS)],
                    )
            except Exception:
                succeeded = False
                _logger.warning(
                    "Landing traffic snapshot remains pending for retry.",
                    exc_info=True,
                )
        return succeeded
