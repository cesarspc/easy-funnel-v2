"""COD form presentation modes for a Landing (Requirement 3.16).

Mirrors the `landings_form_presentation_allowed` database check so an
invalid value is rejected as a field-specific validation error rather than
a database constraint violation.
"""

from __future__ import annotations

from app.domains.landings.errors import LandingValidationError

FORM_PRESENTATION_INLINE = "inline"
FORM_PRESENTATION_MODAL = "modal"

ALLOWED_FORM_PRESENTATIONS = frozenset({FORM_PRESENTATION_INLINE, FORM_PRESENTATION_MODAL})


def validate_form_presentation(raw_presentation: str) -> str:
    """Return the presentation unchanged, or raise for an unsupported value."""
    if raw_presentation not in ALLOWED_FORM_PRESENTATIONS:
        raise LandingValidationError(
            "form_presentation",
            "Form presentation must be 'inline' or 'modal'.",
        )
    return raw_presentation
