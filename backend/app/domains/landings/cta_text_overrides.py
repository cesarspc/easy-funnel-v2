"""Per-CTA-position text override (extends Requirements 3.9-3.15).

A landing's `cta_text` (see `app.domains.landings`) sets the default label
every CTA band renders. `cta_text_overrides` lets the merchant replace that
label for specific 1-based CTA positions only — e.g. "Lo quiero ahora" on the
second CTA while every other CTA keeps the landing's default text.

Stored as a JSON object mapping the position (as a string key, since JSON
object keys are always strings) to its override text. An absent key means
"no override for this position"; the renderer falls back to `cta_text`, then
to the computed default label.

Pure functions only: no I/O, no Prisma.
"""

from __future__ import annotations

from app.domains.landings.errors import LandingValidationError

#: Same bound as `cta_text` (Landing.ctaText), so no override can outgrow the
#: column that stores it.
OVERRIDE_TEXT_MAX = 60


def validate_cta_text_overrides(raw: dict[object, object]) -> dict[str, str]:
    """Validate a merchant-submitted overrides map.

    `raw` keys are coerced to `int` positions (accepting either JSON string
    keys or int keys, since both arrive depending on the caller) and must be
    positive; values must be non-empty, non-blank strings within
    `OVERRIDE_TEXT_MAX`. An empty map is valid and means "no overrides".
    """
    if not isinstance(raw, dict):
        raise LandingValidationError(
            "cta_text_overrides", "CTA text overrides must be an object keyed by position."
        )

    result: dict[str, str] = {}
    for raw_key, raw_value in raw.items():
        try:
            position = int(raw_key)
        except (TypeError, ValueError) as exc:
            raise LandingValidationError(
                "cta_text_overrides", "Each CTA text override key must be a whole number position."
            ) from exc
        if position < 1:
            raise LandingValidationError(
                "cta_text_overrides", "CTA text override positions must be positive."
            )
        if not isinstance(raw_value, str):
            raise LandingValidationError(
                "cta_text_overrides", "Each CTA text override value must be text."
            )
        text = raw_value.strip()
        if not text:
            raise LandingValidationError(
                "cta_text_overrides",
                "A CTA text override cannot be blank; remove the position instead.",
            )
        if len(text) > OVERRIDE_TEXT_MAX:
            raise LandingValidationError(
                "cta_text_overrides",
                f"CTA text overrides must be {OVERRIDE_TEXT_MAX} characters or fewer.",
            )
        result[str(position)] = text

    return result


def resolve_cta_text(
    position: int,
    *,
    overrides: dict[str, str] | None,
    default_text: str | None,
) -> str | None:
    """Return the label for the CTA at `position` (1-based).

    Precedence: this position's override, then the landing's default
    `cta_text`, then `None` (caller substitutes its computed price label).
    """
    if overrides and str(position) in overrides:
        return overrides[str(position)]
    return default_text
