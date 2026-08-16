"""In-process Upstash-compatible test doubles for the redis module tests.

`FakeRedis` reimplements the commands used by rate limits and Landing traffic
counters deterministically without a running Redis/Upstash instance.
"""

from __future__ import annotations

import asyncio
import time


class FakeRedis:
    """Minimal atomic-increment-with-expiry double mimicking the Lua script."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._hashes: dict[str, dict[str, int]] = {}
        self._sets: dict[str, set[str]] = {}
        self._expires_at: dict[str, float] = {}

    def _expire_if_due(self, key: str) -> None:
        expires_at = self._expires_at.get(key)
        if expires_at is not None and time.monotonic() >= expires_at:
            self._counts.pop(key, None)
            self._hashes.pop(key, None)
            self._sets.pop(key, None)
            self._expires_at.pop(key, None)

    async def eval(self, script: str, keys: list[str], args: list[str]):  # type: ignore[no-untyped-def]
        if "LANDING_TRAFFIC_INCREMENT" in script:
            day_key, days_key = keys
            event_day, field = args
            self._expire_if_due(day_key)
            day_hash = self._hashes.setdefault(day_key, {})
            count = day_hash.get(field, 0) + 1
            day_hash[field] = count
            self._sets.setdefault(days_key, set()).add(event_day)
            has_older = any(stored_day < event_day for stored_day in self._sets[days_key])
            return [count, int(has_older)]

        if "LANDING_TRAFFIC_ACKNOWLEDGE" in script:
            day_key, days_key = keys
            event_day, ttl_seconds = args
            self._expires_at[day_key] = time.monotonic() + float(ttl_seconds)
            await self.srem(days_key, event_day)
            return 1

        # Rate-limit increment script.
        (key,) = keys
        (window_seconds,) = args
        self._expire_if_due(key)
        new_count = self._counts.get(key, 0) + 1
        self._counts[key] = new_count
        if new_count == 1:
            self._expires_at[key] = time.monotonic() + float(window_seconds)
        return new_count

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            existed = key in self._counts or key in self._hashes or key in self._sets
            self._counts.pop(key, None)
            self._hashes.pop(key, None)
            self._sets.pop(key, None)
            self._expires_at.pop(key, None)
            deleted += int(existed)
        return deleted

    async def hgetall(self, key: str) -> dict[str, str]:
        self._expire_if_due(key)
        return {field: str(value) for field, value in self._hashes.get(key, {}).items()}

    async def smembers(self, key: str) -> list[str]:
        self._expire_if_due(key)
        return sorted(self._sets.get(key, set()))

    async def srem(self, key: str, *members: str) -> int:
        stored = self._sets.get(key)
        if stored is None:
            return 0
        removed = sum(member in stored for member in members)
        stored.difference_update(members)
        if not stored:
            self._sets.pop(key, None)
        return removed

    async def ttl(self, key: str) -> int:
        self._expire_if_due(key)
        expires_at = self._expires_at.get(key)
        if expires_at is None:
            return -1
        return max(0, int(expires_at - time.monotonic()))

    def force_expire_now(self, key: str) -> None:
        """Test helper: simulate the window elapsing without waiting real time."""
        self._expires_at[key] = time.monotonic() - 1

    def hash_values(self, key: str) -> dict[str, int]:
        """Test helper exposing one Redis hash without changing it."""
        self._expire_if_due(key)
        return dict(self._hashes.get(key, {}))


class FakeUnavailableRedis:
    """Test double simulating an unreachable Redis/Upstash endpoint."""

    async def eval(self, script: str, keys: list[str], args: list[str]) -> int:
        del script, keys, args
        raise ConnectionError("Redis is unavailable")

    async def hgetall(self, key: str) -> dict[str, str]:
        del key
        raise ConnectionError("Redis is unavailable")

    async def smembers(self, key: str) -> list[str]:
        del key
        raise ConnectionError("Redis is unavailable")

    async def srem(self, key: str, *members: str) -> int:
        del key, members
        raise ConnectionError("Redis is unavailable")


class FakeHangingRedis:
    """Test double for a Redis request that never produces a response."""

    async def smembers(self, key: str) -> list[str]:
        del key
        await asyncio.Event().wait()
        return []  # pragma: no cover - the caller must cancel first
