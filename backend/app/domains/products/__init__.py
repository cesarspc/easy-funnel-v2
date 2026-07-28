"""Product domain: field validation and lifecycle transition rules.

Pure functions only — no I/O. `ProductLifecycleService` (app/services)
composes these with repositories inside Prisma transactions.
"""

from app.domains.products.errors import (
    DuplicateSkuError,
    InvalidProductTransitionError,
    ProductNotFoundError,
    ProductValidationError,
    RetiredProductError,
)
from app.domains.products.lifecycle import (
    next_status_on_activate,
    next_status_on_pause,
    next_status_on_retire,
)
from app.domains.products.validation import (
    ALLOWED_CREATION_STATUSES,
    validate_creation_status,
    validate_description,
    validate_name,
    validate_price,
    validate_sku,
)

__all__ = [
    "ProductValidationError",
    "DuplicateSkuError",
    "ProductNotFoundError",
    "InvalidProductTransitionError",
    "RetiredProductError",
    "validate_name",
    "validate_description",
    "validate_price",
    "validate_sku",
    "validate_creation_status",
    "ALLOWED_CREATION_STATUSES",
    "next_status_on_activate",
    "next_status_on_pause",
    "next_status_on_retire",
]
