"""Business calendar conventions for the Colombia-only v1 storefront."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

COLOMBIA_TIME_ZONE_NAME = "America/Bogota"
COLOMBIA_TIME_ZONE = timezone(timedelta(hours=-5), name=COLOMBIA_TIME_ZONE_NAME)


def colombia_today(*, now: datetime | None = None) -> date:
    """Return the Colombia calendar date for an instant (UTC now by default)."""
    instant = now or datetime.now(COLOMBIA_TIME_ZONE)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=COLOMBIA_TIME_ZONE)
    return instant.astimezone(COLOMBIA_TIME_ZONE).date()
