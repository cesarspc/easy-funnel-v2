"""Landing/banner domain errors (no HTTP knowledge; mapped at the API layer)."""

from __future__ import annotations


class LandingValidationError(Exception):
    """Field-specific validation failure (maps to 422)."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


class DuplicateSlugError(Exception):
    """Slug already used by a live or retired landing (Requirement 3.2). Maps to 409."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"Slug '{slug}' is already in use.")
        self.slug = slug


class LandingNotFoundError(Exception):
    def __init__(self, landing_id: int) -> None:
        super().__init__(f"Landing {landing_id} was not found.")
        self.landing_id = landing_id


class BannerNotFoundError(Exception):
    def __init__(self, banner_id: int) -> None:
        super().__init__(f"Banner {banner_id} was not found.")
        self.banner_id = banner_id


class BannerLimitExceededError(Exception):
    """Raised when adding a banner would exceed the 15-banner cap
    (Requirement 3.6). Maps to 409/422."""

    def __init__(self, landing_id: int) -> None:
        super().__init__(f"Landing {landing_id} already has the maximum of 15 banners.")
        self.landing_id = landing_id


class PublicationValidationError(Exception):
    """Raised when publish is requested without 1-15 valid banners or a
    valid CTA config (Requirements 3.19, 3.20). Maps to 422."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
