"""Product field validation (Requirements 2.2, 2.3, 2.4, 2.5, 2.6, 2.10, 2.22).

Pure functions: each returns the normalized value on success or raises
`ProductValidationError` with the offending field name. Called by
`ProductLifecycleService` before any persistence — validation always runs
independently of what the SPA already checked.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.domains.products.errors import ProductValidationError

NAME_MIN_LENGTH = 1
NAME_MAX_LENGTH = 160
DESCRIPTION_MAX_LENGTH = 5000
PRICE_MIN = Decimal("0.01")
PRICE_MAX = Decimal("999999999.99")

ALLOWED_CREATION_STATUSES = frozenset({"active", "paused"})
DEFAULT_CREATION_STATUS = "paused"


def validate_name(raw_name: str) -> str:
    """Trim and validate a product name (1-160 chars after trimming)."""
    trimmed = raw_name.strip()
    if not (NAME_MIN_LENGTH <= len(trimmed) <= NAME_MAX_LENGTH):
        raise ProductValidationError(
            "name", f"Name must be {NAME_MIN_LENGTH}-{NAME_MAX_LENGTH} characters after trimming."
        )
    return trimmed


def validate_description(raw_description: str) -> str:
    """Validate a product description (0-5000 chars)."""
    if len(raw_description) > DESCRIPTION_MAX_LENGTH:
        raise ProductValidationError(
            "description", f"Description must be at most {DESCRIPTION_MAX_LENGTH} characters."
        )
    return raw_description


def validate_price(raw_price: Decimal | str) -> Decimal:
    """Validate a decimal price: 0.01-999,999,999.99, at most 2 decimal places."""
    try:
        price = Decimal(raw_price)
    except InvalidOperation as exc:
        raise ProductValidationError("price", "Price must be a valid decimal number.") from exc

    exponent = price.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -2:
        raise ProductValidationError(
            "price", "Price must have no more than two fractional decimal places."
        )
    if not (PRICE_MIN <= price <= PRICE_MAX):
        raise ProductValidationError("price", f"Price must be between {PRICE_MIN} and {PRICE_MAX}.")
    return price


def validate_sku(raw_sku: str) -> str:
    """Validate a non-empty SKU (uniqueness is checked by the caller against
    the repository, since that requires a database lookup)."""
    trimmed = raw_sku.strip()
    if not trimmed:
        raise ProductValidationError("sku", "SKU must not be empty.")
    return trimmed


def validate_creation_status(raw_status: str | None) -> str:
    """Return the creation status, defaulting to `paused` (Requirement 2.6).

    An explicit status must be one of the statuses an Administrator may
    select at creation time (`active` or `paused`) — `retired` is not a
    valid creation status.
    """
    if raw_status is None:
        return DEFAULT_CREATION_STATUS
    if raw_status not in ALLOWED_CREATION_STATUSES:
        raise ProductValidationError(
            "status",
            f"Status must be one of {sorted(ALLOWED_CREATION_STATUSES)} at creation time.",
        )
    return raw_status
