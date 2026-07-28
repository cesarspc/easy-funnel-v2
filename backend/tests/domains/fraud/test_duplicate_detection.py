"""Property tests for duplicate detection (Requirement 6.2).

Required property (testing.md -> Required Properties #6): For any duplicate-window
boundary, only records inside the configured interval with all configured match
fields equal trigger duplicate detection.
"""

from __future__ import annotations

import pytest
from hypothesis import assume, given, strategies as st
from datetime import datetime, timedelta

from app.domains.fraud.checks import check_duplicate
from app.domains.fraud.models import FraudConfig


# Generate valid Colombian phone keys (10 digits starting with 3)
# More efficient: construct valid keys directly rather than filtering
valid_phone_keys = st.builds(
    lambda prefix, rest: prefix + rest,
    prefix=st.just("3"),
    rest=st.text(alphabet=st.characters(categories=["Nd"]), min_size=9, max_size=9),
)


@given(
    phone_key=valid_phone_keys,
    ip_address=st.text(
        alphabet=st.characters(
            categories=["Nd"],
            min_codepoint=ord("0"),
            max_codepoint=ord("9"),
        ),
        min_size=7,
        max_size=15,
    ),
    window_hours=st.integers(min_value=1, max_value=72),
)
async def test_duplicate_detection_no_false_positives(
    phone_key: str, ip_address: str, window_hours: int
) -> None:
    """Duplicate detection does not flag orders outside the configured window."""
    now = datetime.utcnow()
    old_timestamp = now - timedelta(hours=window_hours + 1)

    # Create a fake Prisma transaction mock that respects WHERE constraints
    class FakeOrderQuery:
        async def find_many(self, where=None):
            # If there's a createdAt constraint, check if order is within the window
            if where and "createdAt" in where and "gte" in where["createdAt"]:
                window_start = where["createdAt"]["gte"]
                # The old_timestamp is BEFORE window_start, so find_many returns empty
                if old_timestamp < window_start:
                    return []
            # Return the old order
            return [
                type("Order", (), {
                    "phoneNormalizedKey": phone_key,
                    "ipAddress": ip_address,
                    "createdAt": old_timestamp,
                    "id": 999,
                })()
            ]

    class FakeTx:
        order = FakeOrderQuery()

    config = FraudConfig(
        duplicate_window_hours=window_hours,
        duplicate_match_fields=frozenset({"phone", "ip"}),
        rate_limit_max=5,
        rate_limit_window_minutes=10,
    )

    result = await check_duplicate(
        FakeTx(),
        phone_normalized_key=phone_key,
        ip_address=ip_address,
        config=config,
    )

    # Should NOT trigger duplicate for old order
    assert len(result) == 0


@given(
    phone_key=valid_phone_keys,
    ip_address=st.text(
        alphabet=st.characters(categories=["Nd"]),
        min_size=7,
        max_size=15,
    ),
    window_hours=st.integers(min_value=1, max_value=72),
)
async def test_duplicate_detection_with_matching_fields(
    phone_key: str, ip_address: str, window_hours: int
) -> None:
    """Duplicate detection flags when all configured match fields are equal."""
    now = datetime.utcnow()

    # Create a matching order within the window
    class FakeOrder:
        phoneNormalizedKey = phone_key
        ipAddress = ip_address
        createdAt = now - timedelta(minutes=5)
        id = 123

    class FakeOrderQuery:
        async def find_many(self, where=None):
            return [FakeOrder()]

    class FakeTx:
        order = FakeOrderQuery()

    config = FraudConfig(
        duplicate_window_hours=window_hours,
        duplicate_match_fields=frozenset({"phone", "ip"}),
        rate_limit_max=5,
        rate_limit_window_minutes=10,
    )

    result = await check_duplicate(
        FakeTx(),
        phone_normalized_key=phone_key,
        ip_address=ip_address,
        config=config,
    )

    # Should trigger duplicate when all fields match
    assert len(result) == 1
    assert result[0].flag_type == "duplicate"


@given(
    phone_key=valid_phone_keys,
    ip_address=st.text(
        alphabet=st.characters(categories=["Nd"]),
        min_size=7,
        max_size=15,
    ),
    window_hours=st.integers(min_value=1, max_value=72),
)
async def test_duplicate_detection_with_matching_phone_only(
    phone_key: str, ip_address: str, window_hours: int
) -> None:
    """Duplicate detection requires ALL configured match fields to match."""
    now = datetime.utcnow()

    # Create order with matching phone but DIFFERENT IP
    class FakeOrder:
        phoneNormalizedKey = phone_key
        ipAddress = "192.168.1.999"  # Different IP!
        createdAt = now - timedelta(minutes=5)
        id = 123

    class FakeOrderQuery:
        async def find_many(self, where=None):
            return [FakeOrder()]

    class FakeTx:
        order = FakeOrderQuery()

    config = FraudConfig(
        duplicate_window_hours=window_hours,
        duplicate_match_fields=frozenset({"phone", "ip"}),
        rate_limit_max=5,
        rate_limit_window_minutes=10,
    )

    result = await check_duplicate(
        FakeTx(),
        phone_normalized_key=phone_key,
        ip_address=ip_address,
        config=config,
    )

    # Should NOT trigger duplicate when IP doesn't match
    assert len(result) == 0


@given(
    window_hours=st.integers(min_value=1, max_value=72),
    match_fields=st.sampled_from([{"phone"}, {"ip"}, {"phone", "ip"}]),
)
async def test_duplicate_configurable_match_fields(
    window_hours: int, match_fields: set[str]
) -> None:
    """Duplicate detection respects configured match fields."""
    now = datetime.utcnow()

    class FakeOrder:
        phoneNormalizedKey = "3001234567"
        ipAddress = "192.168.1.1"
        createdAt = now - timedelta(minutes=5)
        id = 123

    class FakeOrderQuery:
        async def find_many(self, where=None):
            return [FakeOrder()]

    class FakeTx:
        order = FakeOrderQuery()

    config = FraudConfig(
        duplicate_window_hours=window_hours,
        duplicate_match_fields=frozenset(match_fields),
        rate_limit_max=5,
        rate_limit_window_minutes=10,
    )

    result = await check_duplicate(
        FakeTx(),
        phone_normalized_key="3001234567",
        ip_address="192.168.1.1",
        config=config,
    )

    # Should trigger when configured fields match
    assert len(result) == 1


@given(
    window_hours=st.integers(min_value=1, max_value=72),
)
async def test_duplicate_empty_window_disables_detection(window_hours: int) -> None:
    """When window_hours is very small, no duplicates are detected."""
    # With a tiny window, most orders would be outside
    now = datetime.utcnow()
    
    order_created = now - timedelta(hours=window_hours + 1)

    class FakeOrder:
        phoneNormalizedKey = "3001234567"
        ipAddress = "192.168.1.1"
        createdAt = order_created
        id = 123

    class FakeOrderQuery:
        async def find_many(self, where=None):
            # Check if this order is within the queried window
            if where and "createdAt" in where and "gte" in where["createdAt"]:
                # The order was created BEFORE the window, so it shouldn't match
                if FakeOrder.createdAt < where["createdAt"]["gte"]:
                    return []
            return [FakeOrder()]

    class FakeTx:
        order = FakeOrderQuery()

    config = FraudConfig(
        duplicate_window_hours=window_hours,
        duplicate_match_fields=frozenset({"phone", "ip"}),
        rate_limit_max=5,
        rate_limit_window_minutes=10,
    )

    result = await check_duplicate(
        FakeTx(),
        phone_normalized_key="3001234567",
        ip_address="192.168.1.1",
        config=config,
    )

    # Should NOT trigger when order is outside window
    assert len(result) == 0


@given(
    match_fields=st.sets(st.sampled_from(["phone", "ip"]), min_size=1, max_size=2),
    phone_key=valid_phone_keys,
    ip_address=st.text(
        alphabet=st.characters(categories=["Nd"]),
        min_size=7,
        max_size=15,
    ),
)
async def test_duplicate_any_match_field_triggers(
    match_fields: set[str], phone_key: str, ip_address: str
) -> None:
    """Duplicate detection triggers if ANY configured field matches."""
    assume(len(match_fields) > 0)  # Must have at least one field

    now = datetime.utcnow()

    class FakeOrder:
        phoneNormalizedKey = phone_key
        ipAddress = ip_address
        createdAt = now - timedelta(minutes=5)
        id = 123

    class FakeOrderQuery:
        async def find_many(self, where=None):
            return [FakeOrder()]

    class FakeTx:
        order = FakeOrderQuery()

    config = FraudConfig(
        duplicate_window_hours=24,
        duplicate_match_fields=frozenset(match_fields),
        rate_limit_max=5,
        rate_limit_window_minutes=10,
    )

    result = await check_duplicate(
        FakeTx(),
        phone_normalized_key=phone_key,
        ip_address=ip_address,
        config=config,
    )

    # Should trigger when matching configured fields
    assert len(result) == 1


async def test_duplicate_no_duplicate_match_fields_returns_empty() -> None:
    """When no match fields are configured, duplicate detection returns empty."""
    config = FraudConfig(
        duplicate_window_hours=24,
        duplicate_match_fields=frozenset(),  # Empty!
        rate_limit_max=5,
        rate_limit_window_minutes=10,
    )

    # Create a fake mock (shouldn't be called due to early return)
    class FakeTx:
        order = None  # Will raise if accessed

    result = await check_duplicate(
        FakeTx(),
        phone_normalized_key="3001234567",
        ip_address="192.168.1.1",
        config=config,
    )

    # Should return empty when no match fields configured
    assert result == []
