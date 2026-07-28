"""Image pipeline domain errors (no HTTP knowledge; mapped at the API layer)."""

from __future__ import annotations


class ImageValidationError(Exception):
    """Field-specific validation failure (Requirement 4.6). Maps to 422."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


class OpaqueKeyGenerationError(Exception):
    """Raised when both the primary and fallback opaque-key generators fail
    (Requirement 10.20). Upload must be rejected with no partial files and
    no usable banner association."""

    def __init__(self) -> None:
        super().__init__("Both primary and fallback opaque key generation failed.")


class ImagePipelineUnavailableError(Exception):
    """Raised during an upload-pipeline outage (Requirement 4.21). Maps to
    a non-sensitive 503; never leaks internal detail."""

    def __init__(self) -> None:
        super().__init__("The image upload pipeline is temporarily unavailable.")
