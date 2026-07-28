"""Slug validation (Requirements 3.1, 3.2).

Format: lowercase letters, digits, and single hyphens between non-hyphen
characters. Uniqueness against live + retired landings is checked by the
caller against the repository (a database lookup, not a pure function).
"""

from __future__ import annotations

import re

from app.domains.landings.errors import LandingValidationError

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def validate_slug_format(raw_slug: str) -> str:
    """Validate the slug format; return it unchanged on success.

    Rejects empty slugs, leading/trailing hyphens, consecutive hyphens, and
    any character outside lowercase letters and digits.
    """
    if not raw_slug or not _SLUG_PATTERN.match(raw_slug):
        raise LandingValidationError(
            "slug",
            "Slug must contain only lowercase letters, digits, and single "
            "hyphens between non-hyphen characters.",
        )
    return raw_slug
