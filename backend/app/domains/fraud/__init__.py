"""Fraud domain: configuration, blacklist, GeoIP rules, and four fraud checks.

Implements Requirement 6:
- Fraud config with defaults and update validation
- Blacklist add/remove with normalization
- GeoIP rule CRUD
- Four fraud checks: duplicate, blacklist, rate-limit phone/IP, GeoIP
- Multi-flag aggregation
"""

from app.domains.fraud.checks import (
    aggregate_flags,
    check_blacklist,
    check_duplicate,
    check_geoip,
    check_rate_limit_ip,
    check_rate_limit_phone,
)
from app.domains.fraud.errors import (
    BlacklistEntryNotFoundError,
    ConfigNotFoundError,
    DuplicateBlacklistEntryError,
    DuplicateGeoIpRuleError,
    FraudCheckError,
    FraudValidationError,
    GeoIpRuleNotFoundError,
)
from app.domains.fraud.models import (
    ALLOWED_FLAG_TYPES,
    DEFAULT_DUPLICATE_MATCH_FIELDS,
    DEFAULT_DUPLICATE_WINDOW_HOURS,
    DEFAULT_RATE_LIMIT_MAX,
    DEFAULT_RATE_LIMIT_WINDOW_MINUTES,
    FLAG_TYPE_BLACKLIST,
    FLAG_TYPE_DUPLICATE,
    FLAG_TYPE_GEOIP,
    FLAG_TYPE_RATE_LIMIT_IP,
    FLAG_TYPE_RATE_LIMIT_PHONE,
    FraudConfig,
    FraudFlag,
    GeoIpResult,
    RateLimitResult,
)
from app.domains.fraud.settings_validation import (
    ALLOWED_BLACKLIST_ENTRY_TYPES,
    ALLOWED_DUPLICATE_MATCH_FIELDS,
    ALLOWED_GEOIP_ACTIONS,
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

__all__ = [
    "check_duplicate",
    "check_blacklist",
    "check_rate_limit_phone",
    "check_rate_limit_ip",
    "check_geoip",
    "aggregate_flags",
    "FraudCheckError",
    "FraudValidationError",
    "ConfigNotFoundError",
    "BlacklistEntryNotFoundError",
    "GeoIpRuleNotFoundError",
    "DuplicateBlacklistEntryError",
    "DuplicateGeoIpRuleError",
    "ALLOWED_BLACKLIST_ENTRY_TYPES",
    "ALLOWED_DUPLICATE_MATCH_FIELDS",
    "ALLOWED_GEOIP_ACTIONS",
    "validate_blacklist_entry_type",
    "validate_blacklist_ip",
    "validate_blacklist_reason",
    "validate_duplicate_match_fields",
    "validate_duplicate_window_hours",
    "validate_geoip_action",
    "validate_location_code",
    "validate_rate_limit_max",
    "validate_rate_limit_window_minutes",
    "FLAG_TYPE_DUPLICATE",
    "FLAG_TYPE_BLACKLIST",
    "FLAG_TYPE_RATE_LIMIT_PHONE",
    "FLAG_TYPE_RATE_LIMIT_IP",
    "FLAG_TYPE_GEOIP",
    "ALLOWED_FLAG_TYPES",
    "DEFAULT_DUPLICATE_WINDOW_HOURS",
    "DEFAULT_DUPLICATE_MATCH_FIELDS",
    "DEFAULT_RATE_LIMIT_MAX",
    "DEFAULT_RATE_LIMIT_WINDOW_MINUTES",
    "FraudFlag",
    "FraudConfig",
    "GeoIpResult",
    "RateLimitResult",
]
