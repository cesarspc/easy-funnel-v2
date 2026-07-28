"""Orders domain exceptions."""


class OrderValidationError(Exception):
    """Base class for order validation errors."""

    def __init__(self, field: str, message: str) -> None:
        self.field = field
        self.message = message
        super().__init__(f"Validation error for field '{field}': {message}")


class OrderNotFoundError(Exception):
    """Raised when an order is not found."""

    def __init__(self, order_id: int) -> None:
        self.order_id = order_id
        super().__init__(f"Order {order_id} not found")


class InvalidOrderStatusTransition(Exception):
    """Raised when an order status transition is not allowed."""

    def __init__(self, current_status: str, target_status: str) -> None:
        self.current_status = current_status
        self.target_status = target_status
        super().__init__(
            f"Invalid transition from '{current_status}' to '{target_status}'"
        )
