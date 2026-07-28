"""Colombian phone normalization and order field validation (Requirement 5.7)."""

from __future__ import annotations

import re

from app.domains.orders.errors import OrderValidationError, InvalidOrderStatusTransition

# Colombian mobile numbers: national numbers start with '3' and are 10 digits
_PHONE_PATTERN = re.compile(r"^\+?57?3\d{9}$")
_PHONE_DIGITS_PATTERN = re.compile(r"\d")


def normalize_colombian_phone(raw: str) -> str:
    """Normalize a Colombian phone number to +57 + 10 digits.

    Accepts inputs with optional +57 or 57 prefix, with spaces, hyphens,
    parentheses. Returns canonical +57 + 10 digits where the national number
    begins with 3.

    Normalization is idempotent: normalize(normalize(x)) == normalize(x).
    """
    # Strip all non-digit characters, keeping only digits
    digits = "".join(_PHONE_DIGITS_PATTERN.findall(raw)) if raw else ""
    
    # Remove country code if present
    if digits.startswith("57"):
        digits = digits[2:]
    elif digits.startswith("+57"):
        digits = digits[3:]
    
    # Validate: must be 10 digits starting with 3
    if len(digits) != 10 or not digits.startswith("3"):
        raise OrderValidationError(
            "phone",
            "Invalid Colombian phone number. Must be 10 digits starting with 3.",
        )
    
    return f"+57{digits}"


def normalize_colombian_phone_key(raw: str) -> str:
    """Return the matching key for duplicate/blacklist/rate-limit lookups.

    The key is the 10-digit national number (without +57 prefix).
    """
    # Strip all non-digit characters, keeping only digits
    digits = "".join(_PHONE_DIGITS_PATTERN.findall(raw)) if raw else ""
    
    # Remove country code if present
    if digits.startswith("57"):
        digits = digits[2:]
    elif digits.startswith("+57"):
        digits = digits[3:]
    
    # Validate: must be 10 digits starting with 3
    if len(digits) != 10 or not digits.startswith("3"):
        raise OrderValidationError(
            "phone",
            "Invalid Colombian phone number. Must be 10 digits starting with 3.",
        )
    
    return digits


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
