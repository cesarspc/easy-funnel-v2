"""Orders domain: validation, phone normalization, status graph.

Implements Requirement 5:
- Field validation/normalization (name, phone, department, city, address, quantity)
- Phone normalization to E.164 using the merchant-configured phone rules
- Stable matching key for duplicate/blacklist/rate-limit
- Centralized legal status-transition graph
"""

from app.domains.orders.errors import (
    InvalidOrderStatusTransition,
    OrderNotFoundError,
    OrderValidationError,
)
from app.domains.orders.normalization import (
    ADDRESS_MAX,
    ADDRESS_MIN,
    ALLOWED_TRANSITIONS,
    CITY_MAX,
    CITY_MIN,
    DEFAULT_ORDER_STATUS,
    DEPARTMENT_MAX,
    DEPARTMENT_MIN,
    FLAGGED_FRAUD_STATUS,
    NAME_MAX,
    NAME_MIN,
    QUANTITY_MAX,
    QUANTITY_MIN,
    normalize_phone,
    normalize_phone_key,
    validate_address,
    validate_city,
    validate_department,
    validate_name,
    validate_quantity,
    validate_status,
)

__all__ = [
    "OrderValidationError",
    "OrderNotFoundError",
    "InvalidOrderStatusTransition",
    "validate_name",
    "validate_department",
    "validate_city",
    "validate_address",
    "validate_quantity",
    "validate_status",
    "normalize_phone",
    "normalize_phone_key",
    "ALLOWED_TRANSITIONS",
    "DEFAULT_ORDER_STATUS",
    "FLAGGED_FRAUD_STATUS",
    # Length bounds
    "NAME_MIN",
    "NAME_MAX",
    "DEPARTMENT_MIN",
    "DEPARTMENT_MAX",
    "CITY_MIN",
    "CITY_MAX",
    "ADDRESS_MIN",
    "ADDRESS_MAX",
    "QUANTITY_MIN",
    "QUANTITY_MAX",
]
