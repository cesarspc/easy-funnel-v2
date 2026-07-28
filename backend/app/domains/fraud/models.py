"""Fraud flag types and evaluation outcome models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FraudFlag:
    """A single fraud flag triggered by a rule."""

    flag_type: str
    detail: dict


# Flag types (Requirement 6.13-6.15, 10.2)
FLAG_TYPE_DUPLICATE = "duplicate"
FLAG_TYPE_BLACKLIST = "blacklist"
FLAG_TYPE_RATE_LIMIT_PHONE = "rate_limit_phone"
FLAG_TYPE_RATE_LIMIT_IP = "rate_limit_ip"
FLAG_TYPE_GEOIP = "geoip"

ALLOWED_FLAG_TYPES = frozenset(
    {
        FLAG_TYPE_DUPLICATE,
        FLAG_TYPE_BLACKLIST,
        FLAG_TYPE_RATE_LIMIT_PHONE,
        FLAG_TYPE_RATE_LIMIT_IP,
        FLAG_TYPE_GEOIP,
    }
)

# Default fraud configuration (Requirements 6.3, 6.11)
DEFAULT_DUPLICATE_WINDOW_HOURS = 24
DEFAULT_DUPLICATE_MATCH_FIELDS = frozenset({"phone", "ip"})
DEFAULT_RATE_LIMIT_MAX = 5
DEFAULT_RATE_LIMIT_WINDOW_MINUTES = 10


@dataclass(frozen=True)
class FraudConfig:
    """Fraud prevention configuration."""

    duplicate_window_hours: int
    duplicate_match_fields: frozenset[str]
    rate_limit_max: int
    rate_limit_window_minutes: int

    @classmethod
    def from_dict(cls, data: dict) -> FraudConfig:
        """Create from dict (e.g., from database)."""
        return cls(
            duplicate_window_hours=data.get(
                "duplicate_window_hours", DEFAULT_DUPLICATE_WINDOW_HOURS
            ),
            duplicate_match_fields=frozenset(
                data.get("duplicate_match_fields", DEFAULT_DUPLICATE_MATCH_FIELDS)
            ),
            rate_limit_max=data.get("rate_limit_max", DEFAULT_RATE_LIMIT_MAX),
            rate_limit_window_minutes=data.get(
                "rate_limit_window_minutes", DEFAULT_RATE_LIMIT_WINDOW_MINUTES
            ),
        )

    def to_dict(self) -> dict:
        """Convert to dict (e.g., for database)."""
        return {
            "duplicate_window_hours": self.duplicate_window_hours,
            "duplicate_match_fields": list(self.duplicate_match_fields),
            "rate_limit_max": self.rate_limit_max,
            "rate_limit_window_minutes": self.rate_limit_window_minutes,
        }


@dataclass(frozen=True)
class GeoIpResult:
    """Result of GeoIP lookup."""

    country: str | None
    """ISO country code or None if unresolved/unavailable."""

    region: str | None
    """ISO region code or None if not available/unresolved."""

    available: bool
    """True when the database could be queried."""


@dataclass(frozen=True)
class RateLimitResult:
    """Result of rate limit check."""

    count: int
    """Current count including this attempt."""

    limit: int
    """Maximum allowed."""

    triggered: bool
    """True when count exceeds limit."""

    available: bool
    """True when Redis was available."""

    window_minutes: int = 10
    """Time window for rate limiting."""


@dataclass(frozen=True)
class GeoIpRule:
    """GeoIP fraud prevention rule."""

    id: int
    """Unique rule identifier."""

    locationCode: str
    """ISO country or region code to match."""

    action: str
    """Action: 'flag' or 'block'."""

    enabled: bool
    """Whether this rule is active."""
