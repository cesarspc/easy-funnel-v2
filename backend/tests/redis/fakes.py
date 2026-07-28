"""In-process Upstash-compatible test doubles for the redis module tests.

`FakeRedis` reimplements just enough behavior (`eval`, `delete`, `ttl`) to
exercise `app.redis.rate_limit.check_rate_limit` deterministically without a
running Redis/Upstash instance, matching the "Redis test double / Upstash-
compatible mock" tests called for in design.md -> Testing Strategy.
"""

from __future__ import annotations

import time


class FakeRedis:
    """Minimal atomic-increment-with-expiry double mimicking the Lua script."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._expires_at: dict[str, float] = {}

    def _expire_if_due(self, key: str) -> None:
        expires_at = self._expires_at.get(key)
        if expires_at is not None and time.monotonic() >= expires_at:
            self._counts.pop(key, None)
            self._expires_at.pop(key, None)

    async def eval(self, script: str, keys: list[str], args: list[str]) -> int:
        del script  # single script supported; kept for interface parity
        (key,) = keys
        (window_seconds,) = args
        self._expire_if_due(key)
        new_count = self._counts.get(key, 0) + 1
        self._counts[key] = new_count
        if new_count == 1:
            self._expires_at[key] = time.monotonic() + float(window_seconds)
        return new_count

    async def delete(self, key: str) -> None:
        self._counts.pop(key, None)
        self._expires_at.pop(key, None)

    async def ttl(self, key: str) -> int:
        self._expire_if_due(key)
        expires_at = self._expires_at.get(key)
        if expires_at is None:
            return -1
        return max(0, int(expires_at - time.monotonic()))

    def force_expire_now(self, key: str) -> None:
        """Test helper: simulate the window elapsing without waiting real time."""
        self._expires_at[key] = time.monotonic() - 1


class FakeUnavailableRedis:
    """Test double simulating an unreachable Redis/Upstash endpoint."""

    async def eval(self, script: str, keys: list[str], args: list[str]) -> int:
        del script, keys, args
        raise ConnectionError("Redis is unavailable")
