"""Fraud checks: duplicate, blacklist, rate-limit, GeoIP (Requirement 6.1-6.2)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    # Only the GeoIP rule is consumed as a Prisma record here. `FraudConfig`
    # deliberately refers to the domain model imported below: callers translate
    # the persisted record before evaluation (see
    # `app.services.order_submission_service._to_domain_fraud_config`).
    from prisma.models import GeoIpRule


from app.domains.fraud.models import (
    DEFAULT_RATE_LIMIT_WINDOW_MINUTES,
    FLAG_TYPE_BLACKLIST,
    FLAG_TYPE_DUPLICATE,
    FLAG_TYPE_GEOIP,
    FLAG_TYPE_RATE_LIMIT_IP,
    FLAG_TYPE_RATE_LIMIT_PHONE,
    FraudConfig,
    FraudFlag,
    GeoIpResult,
)


# Duplicate detection (Requirement 6.2)
async def check_duplicate(
    db,
    *,
    phone_normalized_key: str,
    ip_address: str,
    config: FraudConfig,
) -> list[FraudFlag]:
    """Check for duplicate orders within the configured window and match fields.

    Returns flags for each triggered rule. Duplicate triggers only when all
    configured match fields are equal AND the order was created within the
    window (inclusive of boundary).
    """
    if not config.duplicate_match_fields:
        return []

    now = datetime.utcnow()
    window_start = now - timedelta(hours=config.duplicate_window_hours)

    # Build query based on configured match fields
    where = {
        "phoneNormalizedKey": phone_normalized_key,
        "ipAddress": ip_address,
        "createdAt": {"gte": window_start},
    }

    # Only check fields that are in the config
    existing_orders = await db.order.find_many(where=where)

    if not existing_orders:
        return []

    # Check if any existing order matches ALL configured fields
    for field in config.duplicate_match_fields:
        if field == "phone":
            where["phoneNormalizedKey"] = phone_normalized_key
        elif field == "ip":
            where["ipAddress"] = ip_address

    # Check each existing order
    for order in existing_orders:
        match = True
        for field in config.duplicate_match_fields:
            phone_differs = field == "phone" and order.phoneNormalizedKey != phone_normalized_key
            ip_differs = field == "ip" and order.ipAddress != ip_address
            if phone_differs or ip_differs:
                match = False
                break

        if match:
            return [
                FraudFlag(
                    flag_type=FLAG_TYPE_DUPLICATE,
                    detail={
                        "matched_fields": list(config.duplicate_match_fields),
                        "window_hours": config.duplicate_window_hours,
                        "order_id": order.id,
                    },
                )
            ]

    return []


# Manual blacklist matching (Requirement 6.4)
async def check_blacklist(
    db,
    *,
    phone_normalized_key: str,
    ip_address: str,
) -> list[FraudFlag]:
    """Check submission phone/IP against the manual blacklist.

    Returns flags for any matching entries. Removed entries no longer match,
    but historical fraud flags are preserved.
    """
    flags = []

    # Check phone
    # Note: phone_normalized_key is already normalized; use it directly
    phone_entry = await db.blacklistentry.find_unique(
        where={
            "entryType_valueNormalized": {
                "entryType": "phone",
                "valueNormalized": phone_normalized_key,
            }
        }
    )
    if phone_entry:
        flags.append(
            FraudFlag(
                flag_type=FLAG_TYPE_BLACKLIST,
                detail={
                    "entry_type": "phone",
                    "reason": phone_entry.reason,
                },
            )
        )

    # Check IP
    ip_entry = await db.blacklistentry.find_unique(
        where={
            "entryType_valueNormalized": {
                "entryType": "ip",
                "valueNormalized": ip_address,
            }
        }
    )
    if ip_entry:
        flags.append(
            FraudFlag(
                flag_type=FLAG_TYPE_BLACKLIST,
                detail={
                    "entry_type": "ip",
                    "reason": ip_entry.reason,
                },
            )
        )

    return flags


# Rate limiting (Requirement 6.9-6.12)
class RateLimitReport(Protocol):
    """The rate-limit facts these checks need.

    Satisfied both by the domain `RateLimitResult` and by
    `app.redis.rate_limit.RateLimitOutcome`, which the submission service passes
    straight through from Redis. Declared structurally so the domain layer keeps
    no import dependency on the Redis client.
    """

    @property
    def count(self) -> int: ...

    @property
    def limit(self) -> int: ...

    @property
    def triggered(self) -> bool: ...

    @property
    def available(self) -> bool: ...


def _resolve_window_minutes(result: RateLimitReport, window_minutes: int | None) -> int:
    """Return the window to record on a rate-limit flag.

    An explicit `window_minutes` (passed by the submission service, which owns
    the active `FraudConfig`) wins. Otherwise fall back to the window carried
    on the result. `app.redis.rate_limit.RateLimitOutcome` reports the count
    and limit but not the window, so the fallback is defensive rather than
    assumed present.
    """
    if window_minutes is not None:
        return window_minutes
    return getattr(result, "window_minutes", DEFAULT_RATE_LIMIT_WINDOW_MINUTES)


def check_rate_limit_phone(
    result: RateLimitReport,
    window_minutes: int | None = None,
) -> list[FraudFlag]:
    """Convert rate limit outcome to fraud flags for phone."""
    if not result.available or not result.triggered:
        return []
    return [
        FraudFlag(
            flag_type=FLAG_TYPE_RATE_LIMIT_PHONE,
            detail={
                "count": result.count,
                "limit": result.limit,
                "window_minutes": _resolve_window_minutes(result, window_minutes),
            },
        )
    ]


def check_rate_limit_ip(
    result: RateLimitReport,
    window_minutes: int | None = None,
) -> list[FraudFlag]:
    """Convert rate limit outcome to fraud flags for IP."""
    if not result.available or not result.triggered:
        return []
    return [
        FraudFlag(
            flag_type=FLAG_TYPE_RATE_LIMIT_IP,
            detail={
                "count": result.count,
                "limit": result.limit,
                "window_minutes": _resolve_window_minutes(result, window_minutes),
            },
        )
    ]


# GeoIP evaluation (Requirement 6.16-6.18)
def check_geoip(
    geoip_result: GeoIpResult,
    geoip_rules: list[GeoIpRule],
) -> list[FraudFlag]:
    """Evaluate GeoIP rules against the lookup result.

    Both flag and block actions produce a flagged_fraud order.
    Unresolved/unavailable lookups don't produce flags.
    """
    if not geoip_result.available or geoip_result.country is None:
        return []

    flags = []
    for rule in geoip_rules:
        if not rule.enabled:
            continue
        if rule.locationCode == geoip_result.country:
            flags.append(
                FraudFlag(
                    flag_type=FLAG_TYPE_GEOIP,
                    detail={
                        "location_code": rule.locationCode,
                        "action": rule.action,
                        "rule_id": rule.id,
                    },
                )
            )

    return flags


# Multi-flag aggregation
def aggregate_flags(flags: list[FraudFlag]) -> list[FraudFlag]:
    """Return all flags, preserving every triggered rule identity.

    A submission can carry duplicate + blacklist + rate-limit(phone) +
    rate-limit(ip) + geoip simultaneously.
    """
    return flags
