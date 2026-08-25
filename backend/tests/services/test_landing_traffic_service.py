"""Redis-to-PostgreSQL Landing traffic reconciliation tests."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from app.services.landing_traffic_service import (
    ACKNOWLEDGED_TTL_SECONDS,
    LandingTrafficService,
    _day_key,
    _days_key,
)

from tests.redis.fakes import FakeRedis, FakeUnavailableRedis


def _service(redis: FakeRedis | FakeUnavailableRedis) -> LandingTrafficService:
    # Repositories only retain this object; every database call is replaced by
    # an AsyncMock in these protocol-level tests.
    service = LandingTrafficService(object(), redis)  # type: ignore[arg-type]
    service._views.persist_redis_snapshot = AsyncMock()  # type: ignore[method-assign]
    service._views.record_fallback = AsyncMock(return_value=1)  # type: ignore[method-assign]
    service._clicks.record_fallback = AsyncMock(return_value=1)  # type: ignore[method-assign]
    return service


async def test_live_day_stays_in_redis_until_reconciliation() -> None:
    redis = FakeRedis()
    service = _service(redis)
    now = datetime(2026, 8, 15, 12, tzinfo=UTC)

    await service.record_view(7, now=now)
    await service.record_view(7, now=now)
    await service.record_cta_click(7, now=now)

    assert redis.hash_values(_day_key(7, "2026-08-15")) == {"views": 2, "cta_clicks": 1}
    service._views.persist_redis_snapshot.assert_not_awaited()  # type: ignore[attr-defined]

    assert await service.reconcile_landing(7, today=now.date()) is True
    service._views.persist_redis_snapshot.assert_awaited_once_with(  # type: ignore[attr-defined]
        7,
        event_date="2026-08-15",
        views=2,
        cta_clicks=1,
    )
    assert await redis.ttl(_day_key(7, "2026-08-15")) == -1
    assert await redis.smembers(_days_key(7)) == ["2026-08-15"]


async def test_first_event_of_next_day_persists_and_acknowledges_previous_day() -> None:
    redis = FakeRedis()
    service = _service(redis)

    await service.record_view(9, now=datetime(2026, 8, 16, 4, 59, tzinfo=UTC))
    await service.record_view(9, now=datetime(2026, 8, 16, 5, 1, tzinfo=UTC))

    service._views.persist_redis_snapshot.assert_awaited_once_with(  # type: ignore[attr-defined]
        9,
        event_date="2026-08-15",
        views=1,
        cta_clicks=0,
    )
    ttl = await redis.ttl(_day_key(9, "2026-08-15"))
    assert ACKNOWLEDGED_TTL_SECONDS - 2 <= ttl <= ACKNOWLEDGED_TTL_SECONDS
    assert await redis.smembers(_days_key(9)) == ["2026-08-16"]


async def test_failed_persistence_keeps_previous_day_pending_without_expiry() -> None:
    redis = FakeRedis()
    service = _service(redis)
    service._views.persist_redis_snapshot.side_effect = RuntimeError("database unavailable")  # type: ignore[attr-defined]

    await service.record_view(11, now=datetime(2026, 8, 16, 4, 59, tzinfo=UTC))
    await service.record_view(11, now=datetime(2026, 8, 16, 5, 1, tzinfo=UTC))

    assert await redis.ttl(_day_key(11, "2026-08-15")) == -1
    assert await redis.smembers(_days_key(11)) == ["2026-08-15", "2026-08-16"]

    service._views.persist_redis_snapshot.side_effect = None  # type: ignore[attr-defined]
    assert (
        await service.reconcile_landing(
            11,
            today=datetime(2026, 8, 16, tzinfo=UTC).date(),
            include_current=False,
        )
        is True
    )
    assert await redis.ttl(_day_key(11, "2026-08-15")) > 0
    assert await redis.smembers(_days_key(11)) == ["2026-08-16"]


async def test_redis_outage_uses_separate_postgresql_fallback_counters() -> None:
    service = _service(FakeUnavailableRedis())

    await service.record_view(13)
    await service.record_cta_click(13)

    service._views.record_fallback.assert_awaited_once_with(13)  # type: ignore[attr-defined]
    service._clicks.record_fallback.assert_awaited_once_with(13)  # type: ignore[attr-defined]
