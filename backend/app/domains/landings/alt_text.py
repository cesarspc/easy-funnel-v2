"""Banner alternative-text validation (Requirements 3.3, 3.4).

Shared by every Banner mutation path — upload (`BannerUploadService`) and
alt-text edit (`LandingManagementService`) — so both enforce the same
trimmed 1-200 character bound the `banners_alt_text_length` database check
constrains.
"""

from __future__ import annotations

from app.domains.landings.errors import LandingValidationError

ALT_TEXT_MIN_LENGTH = 1
ALT_TEXT_MAX_LENGTH = 200


def validate_alt_text(raw_alt_text: str) -> str:
    """Return the trimmed alt text, or raise for an out-of-range length."""
    trimmed = raw_alt_text.strip()
    if not (ALT_TEXT_MIN_LENGTH <= len(trimmed) <= ALT_TEXT_MAX_LENGTH):
        raise LandingValidationError(
            "alt_text",
            f"Alt text must be {ALT_TEXT_MIN_LENGTH}-{ALT_TEXT_MAX_LENGTH} "
            "characters after trimming.",
        )
    return trimmed
