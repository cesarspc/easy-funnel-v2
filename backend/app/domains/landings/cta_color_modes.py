"""Per-CTA-position color mode overrides.

CTA bands normally inherit the colors sampled from their neighbouring
banners. A merchant may instead force one rendered CTA position to a stable
dark or light surface. Only overrides are stored: an absent position means
the existing automatic gradient/solid treatment.
"""

from __future__ import annotations

from app.domains.landings.errors import LandingValidationError

CTA_COLOR_MODE_DEFAULT = "default"
CTA_COLOR_MODE_DARK = "dark"
CTA_COLOR_MODE_LIGHT = "light"
ALLOWED_CTA_COLOR_MODES = frozenset(
    {CTA_COLOR_MODE_DEFAULT, CTA_COLOR_MODE_DARK, CTA_COLOR_MODE_LIGHT}
)


def validate_cta_color_modes(raw: dict[object, object]) -> dict[str, str]:
    """Normalize a position-to-mode map, omitting explicit defaults."""
    if not isinstance(raw, dict):
        raise LandingValidationError(
            "cta_color_modes", "CTA color modes must be an object keyed by position."
        )

    result: dict[str, str] = {}
    for raw_key, raw_value in raw.items():
        try:
            position = int(raw_key)
        except (TypeError, ValueError) as exc:
            raise LandingValidationError(
                "cta_color_modes", "Each CTA color mode key must be a whole number position."
            ) from exc
        if position < 1:
            raise LandingValidationError(
                "cta_color_modes", "CTA color mode positions must be positive."
            )
        if not isinstance(raw_value, str) or raw_value not in ALLOWED_CTA_COLOR_MODES:
            raise LandingValidationError(
                "cta_color_modes", "Each CTA color mode must be default, dark, or light."
            )
        if raw_value != CTA_COLOR_MODE_DEFAULT:
            result[str(position)] = raw_value

    return result


def resolve_cta_color_mode(position: int, modes: dict[str, str] | None) -> str:
    """Resolve one CTA position, falling back to the automatic treatment."""
    if modes:
        mode = modes.get(str(position))
        if mode in (CTA_COLOR_MODE_DARK, CTA_COLOR_MODE_LIGHT):
            return mode
    return CTA_COLOR_MODE_DEFAULT
