"""Administrator-editable fraud setting validation (Requirements 6.6, 6.20-6.24)."""

from __future__ import annotations

import pytest
from app.domains.fraud.errors import FraudValidationError
from app.domains.fraud.settings_validation import (
    validate_blacklist_entry_type,
    validate_blacklist_ip,
    validate_blacklist_reason,
    validate_duplicate_match_fields,
    validate_duplicate_window_hours,
    validate_geoip_action,
    validate_location_code,
    validate_rate_limit_max,
    validate_rate_limit_window_minutes,
)


class TestConfigThresholds:
    @pytest.mark.parametrize(
        "validate",
        [
            validate_duplicate_window_hours,
            validate_rate_limit_max,
            validate_rate_limit_window_minutes,
        ],
    )
    def test_accepts_a_positive_value(self, validate) -> None:  # type: ignore[no-untyped-def]
        assert validate(12) == 12

    @pytest.mark.parametrize(
        ("validate", "field"),
        [
            (validate_duplicate_window_hours, "duplicate_window_hours"),
            (validate_rate_limit_max, "rate_limit_max"),
            (validate_rate_limit_window_minutes, "rate_limit_window_minutes"),
        ],
    )
    @pytest.mark.parametrize("value", [0, -1])
    def test_rejects_a_non_positive_value_with_its_field(
        self,
        validate,  # type: ignore[no-untyped-def]
        field: str,
        value: int,
    ) -> None:
        # Zero must be reported rather than silently ignored, so the dashboard
        # can bind the message to the control that produced it.
        with pytest.raises(FraudValidationError) as exc_info:
            validate(value)

        assert exc_info.value.field == field


class TestDuplicateMatchFields:
    def test_deduplicates_and_orders_the_selection(self) -> None:
        assert validate_duplicate_match_fields(["ip", "phone", "ip"]) == ["ip", "phone"]

    def test_rejects_an_empty_selection(self) -> None:
        with pytest.raises(FraudValidationError) as exc_info:
            validate_duplicate_match_fields([])

        assert exc_info.value.field == "duplicate_match_fields"

    def test_rejects_an_unsupported_field(self) -> None:
        with pytest.raises(FraudValidationError):
            validate_duplicate_match_fields(["phone", "address"])


class TestBlacklistEntry:
    @pytest.mark.parametrize("entry_type", ["phone", "ip"])
    def test_accepts_supported_entry_types(self, entry_type: str) -> None:
        assert validate_blacklist_entry_type(entry_type) == entry_type

    def test_rejects_an_unsupported_entry_type(self) -> None:
        with pytest.raises(FraudValidationError) as exc_info:
            validate_blacklist_entry_type("email")

        assert exc_info.value.field == "entry_type"

    def test_trims_the_reason(self) -> None:
        assert validate_blacklist_reason("  Fraude reiterado  ") == "Fraude reiterado"

    @pytest.mark.parametrize("value", ["", "   ", "x" * 501])
    def test_rejects_an_out_of_range_reason(self, value: str) -> None:
        with pytest.raises(FraudValidationError) as exc_info:
            validate_blacklist_reason(value)

        assert exc_info.value.field == "reason"

    def test_accepts_a_reason_at_the_maximum_length(self) -> None:
        assert len(validate_blacklist_reason("x" * 500)) == 500

    @pytest.mark.parametrize(
        ("submitted", "canonical"),
        [
            ("203.0.113.10", "203.0.113.10"),
            (" 203.0.113.10 ", "203.0.113.10"),
            ("2001:0db8:0000:0000:0000:0000:0000:0001", "2001:db8::1"),
        ],
    )
    def test_canonicalizes_a_valid_ip(self, submitted: str, canonical: str) -> None:
        assert validate_blacklist_ip(submitted) == canonical

    @pytest.mark.parametrize("value", ["", "203.0.113", "999.0.0.1", "not-an-ip"])
    def test_rejects_an_invalid_ip(self, value: str) -> None:
        with pytest.raises(FraudValidationError) as exc_info:
            validate_blacklist_ip(value)

        assert exc_info.value.field == "value_normalized"


class TestGeoIpRule:
    @pytest.mark.parametrize("action", ["flag", "block"])
    def test_accepts_both_actions(self, action: str) -> None:
        assert validate_geoip_action(action) == action

    def test_rejects_an_unsupported_action(self) -> None:
        with pytest.raises(FraudValidationError) as exc_info:
            validate_geoip_action("drop")

        assert exc_info.value.field == "action"

    def test_normalizes_the_location_code_to_uppercase(self) -> None:
        # The resolver reports uppercase codes, so storage must match.
        assert validate_location_code(" ve ") == "VE"

    @pytest.mark.parametrize("value", ["", "C", "x" * 11])
    def test_rejects_an_out_of_range_location_code(self, value: str) -> None:
        with pytest.raises(FraudValidationError) as exc_info:
            validate_location_code(value)

        assert exc_info.value.field == "location_code"
