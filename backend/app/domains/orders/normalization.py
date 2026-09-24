"""Phone normalization and order field validation (Requirement 5.7).

Phone rules (calling code and national number pattern) are merchant settings;
see `app.core.regional`.
"""

from __future__ import annotations

from app.core.regional import PhoneRules, national_phone_digits
from app.domains.orders.errors import OrderValidationError, InvalidOrderStatusTransition


def normalize_phone_key(raw: str, rules: PhoneRules) -> str:
    """Return the national number used for duplicate/blacklist/rate-limit keys.

    Accepts the national number with or without the calling code, with spaces,
    hyphens, parentheses or a leading '+'.
    """
    national = national_phone_digits(raw, rules)
    if national is None:
        raise OrderValidationError(
            "phone",
            f"Invalid phone number for calling code +{rules.country_code}.",
        )
    return national


def normalize_phone(raw: str, rules: PhoneRules) -> str:
    """Normalize a phone number to E.164 (`+<calling code><national number>`).

    Normalization is idempotent: normalize(normalize(x)) == normalize(x).
    """
    return f"+{rules.country_code}{normalize_phone_key(raw, rules)}"


# Field length bounds (Requirements 5.1-5.6)
NAME_MIN = 2
NAME_MAX = 120
DEPARTMENT_MIN = 2
DEPARTMENT_MAX = 100
CITY_MIN = 2
CITY_MAX = 100
ADDRESS_MIN = 5
ADDRESS_MAX = 250
QUANTITY_MIN = 1
QUANTITY_MAX = 99


def validate_name(raw: str) -> str:
    """Validate and trim customer name (Requirement 5.2)."""
    trimmed = raw.strip() if raw else ""
    if len(trimmed) < NAME_MIN:
        raise OrderValidationError(
            "full_name",
            f"Name must contain at least {NAME_MIN} characters.",
        )
    if len(trimmed) > NAME_MAX:
        raise OrderValidationError(
            "full_name",
            f"Name must contain at most {NAME_MAX} characters.",
        )
    return trimmed


def validate_department(raw: str) -> str:
    """Validate and trim department (Requirement 5.3)."""
    trimmed = raw.strip() if raw else ""
    if len(trimmed) < DEPARTMENT_MIN:
        raise OrderValidationError(
            "department",
            f"Department must contain at least {DEPARTMENT_MIN} characters.",
        )
    if len(trimmed) > DEPARTMENT_MAX:
        raise OrderValidationError(
            "department",
            f"Department must contain at most {DEPARTMENT_MAX} characters.",
        )
    return trimmed


def validate_city(raw: str) -> str:
    """Validate and trim city (Requirement 5.3)."""
    trimmed = raw.strip() if raw else ""
    if len(trimmed) < CITY_MIN:
        raise OrderValidationError(
            "city",
            f"City must contain at least {CITY_MIN} characters.",
        )
    if len(trimmed) > CITY_MAX:
        raise OrderValidationError(
            "city",
            f"City must contain at most {CITY_MAX} characters.",
        )
    return trimmed


def validate_address(raw: str) -> str:
    """Validate and trim address (Requirement 5.4)."""
    trimmed = raw.strip() if raw else ""
    if len(trimmed) < ADDRESS_MIN:
        raise OrderValidationError(
            "address",
            f"Address must contain at least {ADDRESS_MIN} characters.",
        )
    if len(trimmed) > ADDRESS_MAX:
        raise OrderValidationError(
            "address",
            f"Address must contain at most {ADDRESS_MAX} characters.",
        )
    return trimmed


def validate_quantity(raw: int) -> int:
    """Validate quantity (Requirement 5.5)."""
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise OrderValidationError("quantity", "Quantity must be an integer.")
    if raw < QUANTITY_MIN:
        raise OrderValidationError(
            "quantity",
            f"Quantity must be at least {QUANTITY_MIN}.",
        )
    if raw > QUANTITY_MAX:
        raise OrderValidationError(
            "quantity",
            f"Quantity must be at most {QUANTITY_MAX}.",
        )
    return raw


def validate_status(current: str, target: str) -> None:
    """Validate that a status transition is legal (Requirement 5.22)."""
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise InvalidOrderStatusTransition(current, target)


# Status graph (Requirement 5.19-5.21)
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"confirmed", "cancelled"},
    "confirmed": {"shipped", "cancelled"},
    "shipped": {"delivered", "cancelled"},
    "flagged_fraud": {"pending", "cancelled"},
}

# Initial status for new orders
DEFAULT_ORDER_STATUS = "pending"

# Flagged fraud status
FLAGGED_FRAUD_STATUS = "flagged_fraud"
