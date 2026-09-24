"""Inclusive dashboard date-range parsing (Requirement 8.11-8.13).

Every analytics query is bounded by a selected range that the requirements
describe as inclusive. Date-only bounds are business days in the merchant's
configured time zone, while timestamps remain stored and compared as
timezone-aware instants.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from app.core.regional import business_zone
from app.domains.analytics.errors import AnalyticsValidationError

_DATE_FORMAT_MESSAGE = "Use an ISO 8601 date (YYYY-MM-DD) or date-time (YYYY-MM-DDTHH:MM:SS) value."


@dataclass(frozen=True)
class DateRange:
    """A resolved, timezone-aware, inclusive `[start, end]` range."""

    start: datetime
    end: datetime
    time_zone: str
    """IANA zone whose calendar days bucket the range's daily figures."""

    @property
    def days(self) -> int:
        """Number of calendar days the range spans, inclusive."""
        return (self.end.date() - self.start.date()).days + 1


def _parse_bound(raw: str, *, field: str) -> datetime:
    if not raw or not raw.strip():
        raise AnalyticsValidationError(field, f"A value is required. {_DATE_FORMAT_MESSAGE}")
    try:
        parsed = datetime.fromisoformat(raw.strip())
    except ValueError as exc:
        raise AnalyticsValidationError(field, _DATE_FORMAT_MESSAGE) from exc
    return parsed


def _is_date_only(raw: str) -> bool:
    return "T" not in raw and ":" not in raw


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def parse_date_range(date_from: str, date_to: str, time_zone: str) -> DateRange:
    """Resolve `date_from`/`date_to` query values into an inclusive range.

    A date-only `date_from` starts at 00:00:00 of that day; a date-only
    `date_to` ends at the last instant before the following midnight, both in
    `time_zone`. Explicit
    date-time bounds are used as given. Raises `AnalyticsValidationError` for a
    malformed bound or a range whose start is after its end.
    """
    raw_from = date_from.strip() if date_from else ""
    raw_to = date_to.strip() if date_to else ""

    zone = business_zone(time_zone)
    start = _as_utc(_parse_bound(raw_from, field="date_from"))
    end = _as_utc(_parse_bound(raw_to, field="date_to"))

    if _is_date_only(raw_from):
        start = datetime.combine(start.date(), time.min, tzinfo=zone)
    if _is_date_only(raw_to):
        # Inclusive upper bound: everything stored on that calendar day, taken
        # as "just before the next midnight" so no fractional second is lost.
        end = datetime.combine(end.date(), time.min, tzinfo=zone) + timedelta(
            days=1, microseconds=-1
        )

    if start > end:
        raise AnalyticsValidationError(
            "date_from", "The start of the range must not be after its end."
        )

    return DateRange(start=start, end=end, time_zone=time_zone)
