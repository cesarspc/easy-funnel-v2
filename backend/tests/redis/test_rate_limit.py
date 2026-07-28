"""Unit tests for the atomic rolling-window rate-limit helper.

Covers Requirements 6.9-6.12 (independent phone/IP rate limits, current
attempt included in the count, unavailable-Redis fallback) and 7.9 (login
rate limiting uses the same primitive).
"""

from __future__ import annotations

from app.redis.rate_limit import (
    check_rate_limit,
    ip_rate_limit_key,
    login_rate_limit_key,
    phone_rate_limit_key,
)

from tests.redis.fakes import FakeRedis, FakeUnavailableRedis


class TestCheckRateLimit:
    async def test_attempt_count_includes_current_attempt(self) -> None:
        redis = FakeRedis()

        outcome = await check_rate_limit(redis, "rl:test", max_attempts=5, window_seconds=600)

        assert outcome.count == 1
        assert outcome.available is True
        assert outcome.triggered is False

    async def test_does_not_trigger_at_exactly_the_configured_maximum(self) -> None:
        redis = FakeRedis()

        outcome = None
        for _ in range(5):
            outcome = await check_rate_limit(redis, "rl:test", max_attempts=5, window_seconds=600)

        assert outcome is not None
        assert outcome.count == 5
        assert outcome.triggered is False

    async def test_triggers_on_the_attempt_after_the_configured_maximum(self) -> None:
        redis = FakeRedis()

        outcome = None
        for _ in range(6):
            outcome = await check_rate_limit(redis, "rl:test", max_attempts=5, window_seconds=600)

        assert outcome is not None
        assert outcome.count == 6
        assert outcome.triggered is True

    async def test_window_expiry_drops_old_attempts(self) -> None:
        redis = FakeRedis()
        for _ in range(5):
            await check_rate_limit(redis, "rl:test", max_attempts=5, window_seconds=600)

        redis.force_expire_now("rl:test")
        outcome = await check_rate_limit(redis, "rl:test", max_attempts=5, window_seconds=600)

        assert outcome.count == 1
        assert outcome.triggered is False

    async def test_unavailable_redis_returns_non_triggering_result(self) -> None:
        redis = FakeUnavailableRedis()

        outcome = await check_rate_limit(redis, "rl:test", max_attempts=5, window_seconds=600)

        assert outcome.available is False
        assert outcome.triggered is False
        assert outcome.count == 0

    async def test_phone_and_ip_counters_are_independent(self) -> None:
        redis = FakeRedis()

        for _ in range(6):
            await check_rate_limit(
                redis, phone_rate_limit_key("3001234567"), max_attempts=5, window_seconds=600
            )
        ip_outcome = await check_rate_limit(
            redis, ip_rate_limit_key("203.0.113.5"), max_attempts=5, window_seconds=600
        )

        assert ip_outcome.count == 1
        assert ip_outcome.triggered is False


class TestKeyHelpers:
    def test_phone_key_is_namespaced(self) -> None:
        assert phone_rate_limit_key("3001234567") == "rl:phone:3001234567"

    def test_ip_key_is_namespaced(self) -> None:
        assert ip_rate_limit_key("203.0.113.5") == "rl:ip:203.0.113.5"

    def test_login_key_is_namespaced(self) -> None:
        assert login_rate_limit_key("admin") == "rl:login:admin"
