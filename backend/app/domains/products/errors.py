"""Product domain errors.

Each carries enough structure for the API layer (task 16) to map it to the
correct HTTP status/field-specific response without the domain layer
knowing anything about HTTP.
"""

from __future__ import annotations


class ProductValidationError(Exception):
    """A field-specific validation failure (maps to 422).

    `field` identifies which input was invalid so the API layer can return
    a field-specific error (Requirement 2.10, 2.22) rather than a generic one.
    """

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


class DuplicateSkuError(Exception):
    """Raised when a SKU is already used by a non-retired or retired product
    (Requirement 2.5). Maps to 409."""

    def __init__(self, sku: str) -> None:
        super().__init__(f"SKU '{sku}' is already in use.")
        self.sku = sku


class ProductNotFoundError(Exception):
    """Raised when an operation targets a product id that does not exist."""

    def __init__(self, product_id: int) -> None:
        super().__init__(f"Product {product_id} was not found.")
        self.product_id = product_id


class RetiredProductError(Exception):
    """Raised when an operation attempts to activate or edit a retired
    product (Requirement 2.17). Maps to 409/403 at the API layer."""

    def __init__(self, product_id: int) -> None:
        super().__init__(f"Product {product_id} is retired and cannot be modified.")
        self.product_id = product_id


class InvalidProductTransitionError(Exception):
    """Raised when an activate/pause/retire request is not legal from the
    product's current status (Requirement 2.20). Maps to 409."""

    def __init__(self, current_status: str, requested_transition: str) -> None:
        super().__init__(f"Cannot {requested_transition} a product with status '{current_status}'.")
        self.current_status = current_status
        self.requested_transition = requested_transition
