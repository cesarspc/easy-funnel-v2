"""Atomic rolling-window rate-limit counters backed by Upstash Redis.

Used by the login rate limiter (Requirement 7.9) and the fraud rate-limit
checks (Requirements 6.9-6.12). Each submission/attempt performs one atomic
increment; the returned count includes the current attempt. If Redis is
unavailable, callers receive a non-triggering, `available=False` result so
the remaining durable checks still run (Requirement 6.12, design doc ->
Fraud Evaluation Design -> Rate limiting).
"""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis as AsyncRedis

# Atomic fixed-window counter: increments the key, and sets the expiry only
# on the first increment of a window so the TTL is not repeatedly extended
# by later attempts within the same window. Runs as a single Lua script so
# the increment + conditional expire is atomic against concurrent callers.
_INCR_WITH_EXPIRY_SCRIPT = """
local count = redis.call("INCR", KEYS[1])
if count == 1 then
  redis.call("EXPIRE", KEYS[1], ARGV[1])
end
return count
"""


@dataclass(frozen=True)
class RateLimitOutcome:
    """Result of one atomic rate-limit increment."""

    count: int
    """Attempt count for the current window, including this attempt."""

    limit: int
    """Configured maximum attempts permitted within the window."""

    triggered: bool
    """True when `count` exceeds `limit` (i.e. this is the (limit+1)th attempt)."""

    available: bool
    """False when Redis could not be reached; `triggered` is always False then."""


def phone_rate_limit_key(phone_normalized_key: str) -> str:
    """Redis key for the phone-number rolling-window counter."""
    return f"rl:phone:{phone_normalized_key}"


def ip_rate_limit_key(ip_address: str) -> str:
    """Redis key for the IP-address rolling-window counter."""
    return f"rl:ip:{ip_address}"


def login_rate_limit_key(identifier: str) -> str:
    """Redis key for the login-attempt rolling-window counter."""
    return f"rl:login:{identifier}"


async def check_rate_limit(
    redis: AsyncRedis,
    key: str,
    *,
    max_attempts: int,
    window_seconds: int,
) -> RateLimitOutcome:
    """Atomically increment `key` and report whether the attempt exceeds the limit.

    The window resets `window_seconds` after the first attempt in that window.
    A Redis outage is treated as unavailable/non-triggering rather than raised,
    so evaluation of the remaining fraud/auth checks is never blocked.
    """
    try:
        raw_count = await redis.eval(
            _INCR_WITH_EXPIRY_SCRIPT,
            keys=[key],
            args=[str(window_seconds)],
        )
    except Exception:
        return RateLimitOutcome(count=0, limit=max_attempts, triggered=False, available=False)

    count = int(raw_count)
    return RateLimitOutcome(
        count=count,
        limit=max_attempts,
        triggered=count > max_attempts,
        available=True,
    )
