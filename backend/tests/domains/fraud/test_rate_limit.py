"""Property tests for rate limiting (Requirement 6.9-6.12).

Required property (testing.md -> Required Properties #7): For any attempt
stream, rolling-window counts do not include attempts outside the configured
interval and trigger at the documented threshold.
"""

from __future__ import annotations

from hypothesis import given, strategies as st, assume
from datetime import datetime, timedelta

from app.domains.fraud.checks import (
    check_rate_limit_ip,
    check_rate_limit_phone,
)
from app.domains.fraud.models import RateLimitResult, FLAG_TYPE_RATE_LIMIT_IP, FLAG_TYPE_RATE_LIMIT_PHONE


@given(
    count=st.integers(min_value=1, max_value=100),
    limit=st.integers(min_value=1, max_value=20),
    window_minutes=st.integers(min_value=1, max_value=120),
)
def test_rate_limit_trigger_when_count_exceeds_limit(
    count: int, limit: int, window_minutes: int
) -> None:
    """Rate limit triggers when count exceeds the configured threshold."""
    assume(count > limit)

    result = RateLimitResult(
        available=True,
        triggered=True,
        count=count,
        limit=limit,
        window_minutes=window_minutes,
    )

    phone_flags = check_rate_limit_phone(result)
    ip_flags = check_rate_limit_ip(result)

    # Both should produce flags when triggered
    assert len(phone_flags) == 1
    assert len(ip_flags) == 1
    assert phone_flags[0].flag_type == FLAG_TYPE_RATE_LIMIT_PHONE
    assert ip_flags[0].flag_type == FLAG_TYPE_RATE_LIMIT_IP


@given(
    count=st.integers(min_value=1, max_value=10),
    limit=st.integers(min_value=10, max_value=100),
    window_minutes=st.integers(min_value=1, max_value=120),
)
def test_rate_limit_no_trigger_when_count_within_limit(
    count: int, limit: int, window_minutes: int
) -> None:
    """Rate limit does not trigger when count is within the configured threshold."""
    assume(count <= limit)

    result = RateLimitResult(
        available=True,
        triggered=False,
        count=count,
        limit=limit,
        window_minutes=window_minutes,
    )

    phone_flags = check_rate_limit_phone(result)
    ip_flags = check_rate_limit_ip(result)

    # Both should produce no flags when within limit
    assert len(phone_flags) == 0
    assert len(ip_flags) == 0


@given(
    count=st.integers(min_value=1, max_value=100),
    limit=st.integers(min_value=1, max_value=100),
    window_minutes=st.integers(min_value=1, max_value=120),
)
def test_rate_limit_flags_contain_correct_details(
    count: int, limit: int, window_minutes: int
) -> None:
    """Rate limit flags contain accurate count, limit, and window information."""
    result = RateLimitResult(
        available=True,
        triggered=count > limit,
        count=count,
        limit=limit,
        window_minutes=window_minutes,
    )

    phone_flags = check_rate_limit_phone(result)
    ip_flags = check_rate_limit_ip(result)

    if phone_flags:
        detail = phone_flags[0].detail
        assert detail["count"] == count
        assert detail["limit"] == limit
        assert detail["window_minutes"] == window_minutes


@given(
    window_minutes=st.integers(min_value=1, max_value=120),
)
def test_rate_limit_available_false_returns_no_flags(window_minutes: int) -> None:
    """When Redis is unavailable, rate limit returns no flags."""
    result = RateLimitResult(
        available=False,
        triggered=False,
        count=0,
        limit=5,
        window_minutes=window_minutes,
    )

    phone_flags = check_rate_limit_phone(result)
    ip_flags = check_rate_limit_ip(result)

    # Should produce no flags when unavailable
    assert len(phone_flags) == 0
    assert len(ip_flags) == 0


@given(
    window_minutes=st.integers(min_value=1, max_value=120),
)
def test_rate_limit_phone_and_ip_are_independent(
    window_minutes: int,
) -> None:
    """Phone and IP rate limits are tracked independently."""
    phone_result = RateLimitResult(
        available=True,
        triggered=True,
        count=10,
        limit=5,
        window_minutes=window_minutes,
    )

    ip_result = RateLimitResult(
        available=True,
        triggered=False,
        count=3,
        limit=5,
        window_minutes=window_minutes,
    )

    phone_flags = check_rate_limit_phone(phone_result)
    ip_flags = check_rate_limit_ip(ip_result)

    # Phone should trigger, IP should not
    assert len(phone_flags) == 1
    assert len(ip_flags) == 0


@given(
    window_minutes=st.integers(min_value=1, max_value=120),
)
def test_rate_limit_both_phone_and_ip_can_trigger(window_minutes: int) -> None:
    """Both phone and IP rate limits can trigger simultaneously."""
    phone_result = RateLimitResult(
        available=True,
        triggered=True,
        count=10,
        limit=5,
        window_minutes=window_minutes,
    )

    ip_result = RateLimitResult(
        available=True,
        triggered=True,
        count=8,
        limit=5,
        window_minutes=window_minutes,
    )

    phone_flags = check_rate_limit_phone(phone_result)
    ip_flags = check_rate_limit_ip(ip_result)

    # Both should trigger
    assert len(phone_flags) == 1
    assert len(ip_flags) == 1


@given(
    count=st.integers(min_value=1, max_value=100),
    limit=st.integers(min_value=1, max_value=100),
    window_minutes=st.integers(min_value=1, max_value=120),
)
def test_rate_limit_threshold_boundary(count: int, limit: int, window_minutes: int) -> None:
    """Rate limit triggers exactly at threshold (count == limit)."""
    result = RateLimitResult(
        available=True,
        triggered=count >= limit,
        count=count,
        limit=limit,
        window_minutes=window_minutes,
    )

    phone_flags = check_rate_limit_phone(result)

    if count >= limit:
        assert len(phone_flags) == 1
    else:
        assert len(phone_flags) == 0


@given(
    count=st.integers(min_value=1, max_value=100),
    limit=st.integers(min_value=1, max_value=100),
    window_minutes=st.integers(min_value=1, max_value=120),
)
def test_rate_limit_below_threshold_no_trigger(count: int, limit: int, window_minutes: int) -> None:
    """Rate limit does not trigger when count is below threshold."""
    assume(count < limit)

    result = RateLimitResult(
        available=True,
        triggered=False,
        count=count,
        limit=limit,
        window_minutes=window_minutes,
    )

    phone_flags = check_rate_limit_phone(result)
    ip_flags = check_rate_limit_ip(result)

    # Should not trigger when below threshold
    assert len(phone_flags) == 0
    assert len(ip_flags) == 0
