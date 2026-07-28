"""How a Landing paints its CTA bands (Requirement 3.16, band rendering).

Mirrors the `landings_cta_band_style_allowed` database check so an invalid
value is rejected as a field-specific validation error rather than a database
constraint violation.

Two styles, both derived from the *same* edge colors — this setting changes
only how those colors are painted, never how they are extracted or paired:

- `gradient` (default): fade from the bottom edge of the banner above to the
  top edge of the banner below, so the band reads as a continuation of the
  artwork. Right when the two edges are close.
- `solid`: fill the whole band with the midpoint of the two edges
  (`CtaBandBackground.blend_color`), no fade. Right when the two edges are far
  apart — a long ramp between, say, deep navy and warm gray reads as a smear,
  where one deliberate color reads as a designed divider.

Which of those a given banner sequence needs is a judgement about the artwork,
not something the pixels can settle, so it is a per-landing property the
merchant sets alongside `cta_mode` and `form_presentation`.
"""

from __future__ import annotations

from app.domains.landings.errors import LandingValidationError

CTA_BAND_STYLE_GRADIENT = "gradient"
CTA_BAND_STYLE_SOLID = "solid"

ALLOWED_CTA_BAND_STYLES = frozenset({CTA_BAND_STYLE_GRADIENT, CTA_BAND_STYLE_SOLID})


def validate_cta_band_style(raw_style: str) -> str:
    """Return the style unchanged, or raise for an unsupported value."""
    if raw_style not in ALLOWED_CTA_BAND_STYLES:
        raise LandingValidationError(
            "cta_band_style",
            "CTA band style must be 'gradient' or 'solid'.",
        )
    return raw_style
