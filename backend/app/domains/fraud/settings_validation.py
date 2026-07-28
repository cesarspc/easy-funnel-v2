"""Validation for Administrator-editable fraud settings (Requirements 6.6, 6.7, 6.20-6.24).

Mirrors the database check constraints (`fraud_config_*`,
`blacklist_entries_type_allowed`, `blacklist_entries_reason_length`,
`geoip_rules_action_allowed`) so an invalid value is rejected as a
field-specific error before any write, leaving the active configuration in
place (Requirement 6.24, 10.1-10.2).
"""

from __future__ import annotations

from ipaddress import ip_address

from app.domains.fraud.errors import FraudValidationError

ALLOWED_DUPLICATE_MATCH_FIELDS = frozenset({"phone", "ip"})
ALLOWED_BLACKLIST_ENTRY_TYPES = frozenset({"phone", "ip"})
ALLOWED_GEOIP_ACTIONS = frozenset({"flag", "block"})

REASON_MIN_LENGTH = 1
REASON_MAX_LENGTH = 500
LOCATION_CODE_MIN_LENGTH = 2
LOCATION_CODE_MAX_LENGTH = 10


def _validate_positive(value: int, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise FraudValidationError(field, "Must be a positive whole number.")
    return value


def validate_duplicate_window_hours(value: int) -> int:
    """Validate the Duplicate_Window in hours (Requirement 6.20)."""
    return _validate_positive(value, field="duplicate_window_hours")


def validate_rate_limit_max(value: int) -> int:
    """Validate the Rate_Limit attempt maximum (Requirement 6.21)."""
    return _validate_positive(value, field="rate_limit_max")


def validate_rate_limit_window_minutes(value: int) -> int:
    """Validate the Rate_Limit rolling window in minutes (Requirement 6.21)."""
    return _validate_positive(value, field="rate_limit_window_minutes")


def validate_duplicate_match_fields(values: list[str]) -> list[str]:
    """Validate the Duplicate_Match_Fields set (Requirement 6.2, 6.20).

    Returns the fields deduplicated in a stable order; rejects an empty set and
    any field outside the supported phone/IP pair.
    """
    if not values:
        raise FraudValidationError(
            "duplicate_match_fields", "Select at least one field to match on."
        )
    unsupported = [value for value in values if value not in ALLOWED_DUPLICATE_MATCH_FIELDS]
    if unsupported:
        raise FraudValidationError(
            "duplicate_match_fields", "Supported fields are 'phone' and 'ip'."
        )
    return sorted(set(values))


def validate_blacklist_entry_type(value: str) -> str:
    """Validate a Manual_Blacklist entry type (Requirement 6.6)."""
    if value not in ALLOWED_BLACKLIST_ENTRY_TYPES:
        raise FraudValidationError("entry_type", "Must be 'phone' or 'ip'.")
    return value


def validate_blacklist_reason(value: str) -> str:
    """Validate a Manual_Blacklist reason (Requirement 6.6)."""
    trimmed = (value or "").strip()
    if not (REASON_MIN_LENGTH <= len(trimmed) <= REASON_MAX_LENGTH):
        raise FraudValidationError(
            "reason", f"Must be {REASON_MIN_LENGTH}-{REASON_MAX_LENGTH} characters."
        )
    return trimmed


def validate_blacklist_ip(value: str) -> str:
    """Validate and canonicalize a Manual_Blacklist IP value.

    The Manual_Blacklist_Validity_Requirements accept a syntactically valid
    canonical IPv4 or IPv6 address; the canonical string form is stored so a
    request IP compares equal regardless of the notation an Administrator typed
    (Requirement 6.6, 6.24).
    """
    trimmed = (value or "").strip()
    try:
        return str(ip_address(trimmed))
    except ValueError as exc:
        raise FraudValidationError(
            "value_normalized", "Must be a valid IPv4 or IPv6 address."
        ) from exc


def validate_geoip_action(value: str) -> str:
    """Validate a GeoIP_Rule action (Requirement 6.22, 6.23)."""
    if value not in ALLOWED_GEOIP_ACTIONS:
        raise FraudValidationError("action", "Must be 'flag' or 'block'.")
    return value


def validate_location_code(value: str) -> str:
    """Validate a GeoIP_Rule location code (Requirement 6.22).

    Country/region codes are compared against the resolver's uppercase output,
    so the stored value is normalized to uppercase here.
    """
    trimmed = (value or "").strip().upper()
    if not (LOCATION_CODE_MIN_LENGTH <= len(trimmed) <= LOCATION_CODE_MAX_LENGTH):
        raise FraudValidationError(
            "location_code",
            f"Must be {LOCATION_CODE_MIN_LENGTH}-{LOCATION_CODE_MAX_LENGTH} characters.",
        )
    return trimmed
