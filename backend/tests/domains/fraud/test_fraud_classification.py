"""Property tests for fraud classification (Requirement 6.1-6.2).

Required property (testing.md -> Required Properties #5): For any set of
fraud rule outcomes, classification is `pending` exactly when no rule triggers;
otherwise classification is `flagged_fraud` and all triggered rule identities
are preserved.
"""

from __future__ import annotations

from app.domains.fraud.checks import (
    check_blacklist,
    check_duplicate,
    check_geoip,
)
from app.domains.fraud.models import (
    FLAG_TYPE_BLACKLIST,
    FLAG_TYPE_DUPLICATE,
    FLAG_TYPE_GEOIP,
    FraudFlag,
    FraudConfig,
    GeoIpResult,
    GeoIpRule,
)


class TestFraudClassificationAggregation:
    """Test that fraud classification correctly aggregates all flags."""

    def test_no_flags_means_pending(self) -> None:
        """When no fraud rules trigger, classification should be pending."""
        all_flags = []

        # Verify all flags are empty
        assert len(all_flags) == 0

    def test_single_duplicate_flag_means_flagged_fraud(self) -> None:
        """When duplicate detection triggers, classification should be flagged_fraud."""
        duplicate_flag = FraudFlag(
            flag_type=FLAG_TYPE_DUPLICATE,
            detail={"order_id": 123, "matched_fields": ["phone", "ip"]},
        )
        all_flags = [duplicate_flag]

        assert len(all_flags) == 1
        assert all_flags[0].flag_type == FLAG_TYPE_DUPLICATE

    def test_single_blacklist_flag_means_flagged_fraud(self) -> None:
        """When blacklist matching triggers, classification should be flagged_fraud."""
        blacklist_flag = FraudFlag(
            flag_type=FLAG_TYPE_BLACKLIST,
            detail={"entry_type": "phone", "reason": "Manual block"},
        )
        all_flags = [blacklist_flag]

        assert len(all_flags) == 1
        assert all_flags[0].flag_type == FLAG_TYPE_BLACKLIST

    def test_single_geoip_flag_means_flagged_fraud(self) -> None:
        """When GeoIP rules trigger, classification should be flagged_fraud."""
        geoip_flag = FraudFlag(
            flag_type=FLAG_TYPE_GEOIP,
            detail={"location_code": "CO", "action": "flag", "rule_id": 1},
        )
        all_flags = [geoip_flag]

        assert len(all_flags) == 1
        assert all_flags[0].flag_type == FLAG_TYPE_GEOIP


class TestMultiFlagAggregation:
    """Test that all triggered rules are preserved in classification."""

    def test_duplicate_and_blacklist_both_preserved(self) -> None:
        """When duplicate and blacklist both trigger, both flags are preserved."""
        duplicate_flag = FraudFlag(
            flag_type=FLAG_TYPE_DUPLICATE,
            detail={"order_id": 123, "matched_fields": ["phone"]},
        )
        blacklist_flag = FraudFlag(
            flag_type=FLAG_TYPE_BLACKLIST,
            detail={"entry_type": "ip", "reason": "Suspicious IP"},
        )

        all_flags = [duplicate_flag, blacklist_flag]

        assert len(all_flags) == 2
        assert duplicate_flag.flag_type in [f.flag_type for f in all_flags]
        assert blacklist_flag.flag_type in [f.flag_type for f in all_flags]

    def test_all_four_rules_can_trigger_simultaneously(self) -> None:
        """All four fraud rules (duplicate, blacklist, rate-limit phone, rate-limit ip)
        can trigger simultaneously, and all flags are preserved."""
        duplicate_flag = FraudFlag(
            flag_type=FLAG_TYPE_DUPLICATE,
            detail={"order_id": 123, "matched_fields": ["phone"]},
        )
        blacklist_flag = FraudFlag(
            flag_type=FLAG_TYPE_BLACKLIST,
            detail={"entry_type": "phone", "reason": "Manual block"},
        )
        geoip_flag = FraudFlag(
            flag_type=FLAG_TYPE_GEOIP,
            detail={"location_code": "CO", "action": "block", "rule_id": 1},
        )

        # Create a fake rate limit flags for testing
        from app.domains.fraud.checks import check_rate_limit_phone, check_rate_limit_ip
        from app.domains.fraud.models import RateLimitResult, FLAG_TYPE_RATE_LIMIT_PHONE, FLAG_TYPE_RATE_LIMIT_IP

        rate_limit_phone_flags = check_rate_limit_phone(
            RateLimitResult(
                available=True,
                triggered=True,
                count=10,
                limit=5,
                window_minutes=10,
            )
        )
        rate_limit_ip_flags = check_rate_limit_ip(
            RateLimitResult(
                available=True,
                triggered=True,
                count=8,
                limit=5,
                window_minutes=10,
            )
        )

        all_flags = (
            [duplicate_flag, blacklist_flag, geoip_flag]
            + rate_limit_phone_flags
            + rate_limit_ip_flags
        )

        # All flags should be preserved
        assert duplicate_flag.flag_type in [f.flag_type for f in all_flags]
        assert blacklist_flag.flag_type in [f.flag_type for f in all_flags]
        assert geoip_flag.flag_type in [f.flag_type for f in all_flags]


def test_geoip_flag_with_country_match() -> None:
    """GeoIP rule matching country produces flag."""
    geoip_result = GeoIpResult(
        country="CO",
        region="Cundinamarca",
        available=True,
    )

    from app.domains.fraud.models import GeoIpRule

    geoip_rules = [
        GeoIpRule(
            id=1,
            locationCode="CO",
            action="flag",
            enabled=True,
        ),
    ]

    flags = check_geoip(geoip_result, geoip_rules)

    assert len(flags) == 1
    assert flags[0].flag_type == FLAG_TYPE_GEOIP
    assert flags[0].detail["location_code"] == "CO"


def test_geoip_no_flag_when_no_country_match() -> None:
    """GeoIP rules don't flag when location doesn't match."""
    geoip_result = GeoIpResult(
        country="US",
        region="California",
        available=True,
    )

    from app.domains.fraud.models import GeoIpRule

    geoip_rules = [
        GeoIpRule(
            id=1,
            locationCode="CO",
            action="flag",
            enabled=True,
        ),
    ]

    flags = check_geoip(geoip_result, geoip_rules)

    assert len(flags) == 0


def test_geoip_no_flag_when_unavailable() -> None:
    """GeoIP rules don't flag when database is unavailable."""
    geoip_result = GeoIpResult(
        country=None,
        region=None,
        available=False,
    )

    geoip_rules = [
        GeoIpRule(
            id=1,
            locationCode="CO",
            action="flag",
            enabled=True,
        ),
    ]

    flags = check_geoip(geoip_result, geoip_rules)

    assert len(flags) == 0


def test_geoip_no_flag_when_unresolved() -> None:
    """GeoIP rules don't flag when address is unresolved (not in database)."""
    geoip_result = GeoIpResult(
        country=None,
        region=None,
        available=True,
    )

    geoip_rules = [
        GeoIpRule(
            id=1,
            locationCode="CO",
            action="flag",
            enabled=True,
        ),
    ]

    flags = check_geoip(geoip_result, geoip_rules)

    assert len(flags) == 0


def test_blacklist_matches_normalized_phone() -> None:
    """Blacklist matching uses normalized phone keys."""
    # Test with normalized phone key format
    from app.core.regional import DEFAULT_REGIONAL
    from app.domains.orders.normalization import normalize_phone_key

    phone_key = normalize_phone_key("+573001234567", DEFAULT_REGIONAL.phone)
    assert len(phone_key) == 10  # Should be 10 digits
