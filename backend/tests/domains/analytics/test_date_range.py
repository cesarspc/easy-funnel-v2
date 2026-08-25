"""Inclusive dashboard date-range parsing (Requirements 8.11-8.13, 10.2)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.domains.analytics.date_range import parse_date_range
from app.domains.analytics.errors import AnalyticsValidationError


class TestParseDateRange:
    def test_date_only_range_covers_whole_calendar_days(self) -> None:
        date_range = parse_date_range("2026-07-01", "2026-07-24")

        assert date_range.start == datetime(2026, 7, 1, 5, 0, 0, tzinfo=UTC)
        # The upper bound must include an order created late on the final day.
        assert date_range.end == datetime(2026, 7, 25, 4, 59, 59, 999999, tzinfo=UTC)

    def test_colombia_evening_does_not_roll_into_the_next_analytics_day(self) -> None:
        date_range = parse_date_range("2026-07-24", "2026-07-24")
        order_created_at = datetime(2026, 7, 25, 2, 30, tzinfo=UTC)

        assert date_range.start <= order_created_at <= date_range.end

    def test_single_day_range_is_not_empty(self) -> None:
        date_range = parse_date_range("2026-07-24", "2026-07-24")

        assert date_range.start < date_range.end
        assert date_range.days == 1

    def test_explicit_date_times_are_used_as_given(self) -> None:
        date_range = parse_date_range("2026-07-24T08:00:00", "2026-07-24T12:30:00")

        assert date_range.start == datetime(2026, 7, 24, 8, 0, 0, tzinfo=UTC)
        assert date_range.end == datetime(2026, 7, 24, 12, 30, 0, tzinfo=UTC)

    def test_offset_aware_bounds_keep_their_offset(self) -> None:
        date_range = parse_date_range("2026-07-24T00:00:00+00:00", "2026-07-24T23:00:00+00:00")

        assert date_range.start.tzinfo is not None
        assert date_range.end.hour == 23

    def test_days_counts_both_ends(self) -> None:
        assert parse_date_range("2026-07-01", "2026-07-03").days == 3

    @pytest.mark.parametrize("value", ["", "   ", "24-07-2026", "not-a-date", "2026-13-01"])
    def test_malformed_bound_is_a_field_error(self, value: str) -> None:
        with pytest.raises(AnalyticsValidationError) as exc_info:
            parse_date_range(value, "2026-07-24")

        assert exc_info.value.field == "date_from"

    def test_malformed_upper_bound_names_its_own_field(self) -> None:
        with pytest.raises(AnalyticsValidationError) as exc_info:
            parse_date_range("2026-07-01", "yesterday")

        assert exc_info.value.field == "date_to"

    def test_inverted_range_is_rejected(self) -> None:
        with pytest.raises(AnalyticsValidationError) as exc_info:
            parse_date_range("2026-07-24", "2026-07-01")

        assert exc_info.value.field == "date_from"
