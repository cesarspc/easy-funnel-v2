"""Analytics domain errors (no HTTP knowledge; mapped at the API layer)."""

from __future__ import annotations


class AnalyticsValidationError(Exception):
    """Field-specific validation failure for a dashboard query (maps to 422).

    Requirement 10.2: documented type/format constraints on private input are
    validated before use, so a malformed date range is a field error rather
    than an unhandled parse failure.
    """

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message
