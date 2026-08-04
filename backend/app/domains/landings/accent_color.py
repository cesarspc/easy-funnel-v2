"""Per-landing accent color and the palette derived from it.

One color, many shades. The merchant picks a single `#rrggbb` accent and the
Landing chrome needs four values from it: the accent itself (CTA fill, selected
offer fill, focus rings, accent text), a deeper shade for hover/pressed, a very
light tint for the background of an offer tile, and a foreground that is
actually readable on the accent.

Deriving those here rather than letting the merchant set each one is deliberate.
A four-swatch picker is how a public page ends up with white text on a pale
yellow button: every combination has to pass contrast, and only one of the four
is a real brand decision. The merchant chooses the brand color; the chrome
chooses how to stay legible with it.

**The accent's lightness is not purely the merchant's call.** The accent both
carries text (the CTA label sits on it) and *is* text (accent-colored copy on
the page's white surface). A mid-tone color satisfies neither: white text on a
medium purple lands around 3.9:1, and so does near-black text, because neither
foreground is far enough away. Picking a better foreground cannot fix that, so
`derive_accent_palette` darkens the accent until white text on it clears 4.5:1.
The hue survives; only the lightness moves, and only when it has to. That one
guarantee is what lets the palette carry a single `ink` instead of a light/dark
branch that quietly fails in the middle of the range.

The math is shared with the CTA band code (`app.domains.images.edge_color`) so
a landing's accent and its banner-derived bands agree about color.

Pure functions only: no I/O, no Prisma.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.domains.images.edge_color import (
    blend_hex,
    format_hex,
    parse_hex,
    relative_luminance,
)
from app.domains.landings.errors import LandingValidationError

#: The green the Landing chrome shipped with, and the default for any landing
#: that never set an accent.
DEFAULT_ACCENT_COLOR = "#1a7a4c"

#: Canonical stored form: lowercase `#rrggbb`. Mirrors the
#: `landings_accent_color_format` database check. Shorthand `#abc` is accepted
#: on input and expanded, because a merchant pasting a 3-digit hex from a brand
#: guide is not making a mistake.
_ACCENT_PATTERN = re.compile(r"^#[0-9a-f]{6}$")

#: How far the hover shade moves toward black. Enough to register as a state
#: change on a press without reading as a different color.
_DEEP_BLEND_WEIGHT = 0.22

#: How far the tile tint moves toward white. High, because this sits *behind*
#: body text: the tint has to read as "this one is highlighted" while leaving
#: the text on it at full contrast. 10% accent is a touch more present than the
#: 6% the chrome hardcoded before accents were configurable, so a merchant's
#: color is actually visible in the tile without competing with its copy.
_TINT_BLEND_WEIGHT = 0.90

#: WCAG 2.x contrast floor for normal-size text. The accent carries button
#: labels and is itself used as a text color, so this is the binding constraint
#: on how light the accent is allowed to be.
_CONTRAST_FLOOR = 4.5

#: Step size when darkening a too-light accent, and the cap on how many steps
#: are tried. 40 x 0.025 reaches pure black, so the loop always terminates with
#: a passing color.
_DARKEN_STEP = 0.025
_DARKEN_MAX_STEPS = 40

#: The single foreground for text on the accent. The accent is darkened until
#: white text clears the contrast floor on it, so there is no light/dark branch
#: to get wrong (see `_ensure_readable_with_white_text`).
_INK_ON_ACCENT = "#ffffff"

_BLACK = "#000000"
_WHITE = "#ffffff"


@dataclass(frozen=True)
class AccentPalette:
    """Every accent-derived color the Landing chrome paints with.

    Computed server-side and sent whole so the public page never has to do
    color math to render its first paint, and the dashboard preview and the
    live page can never disagree about a shade.
    """

    accent: str
    """The merchant's color: CTA fill, selected offer fill, focus ring, accent text."""

    deep: str
    """Hover/pressed shade of `accent`."""

    tint: str
    """Very light wash of `accent`, for the background of a highlighted offer."""

    ink: str
    """Text color that reads on `accent`."""


def _contrast_ratio(first: str, second: str) -> float:
    first_luminance = relative_luminance(first)
    second_luminance = relative_luminance(second)
    lighter, darker = (
        (first_luminance, second_luminance)
        if first_luminance > second_luminance
        else (second_luminance, first_luminance)
    )
    return (lighter + 0.05) / (darker + 0.05)


def _ensure_readable_with_white_text(color: str) -> str:
    """Darken `color` until white text on it clears the contrast floor.

    A mid-tone accent (a medium purple, a mustard) is the case that breaks the
    obvious approach: picking whichever of black or white contrasts better still
    leaves normal-size text below 4.5:1, because *neither* is far enough away.
    Choosing a foreground cannot fix that — the background has to move.

    Darkening preserves the merchant's hue while making one guarantee hold for
    every possible input: the accent is dark enough to carry white text, and
    therefore also dark enough to be used as text on the page's white surface.
    That is what collapses the palette to a single `ink` instead of a
    light/dark branch that silently fails in the middle of the range.
    """
    if _contrast_ratio(color, _WHITE) >= _CONTRAST_FLOOR:
        return color

    for step in range(1, _DARKEN_MAX_STEPS + 1):
        candidate = blend_hex(color, _BLACK, min(1.0, step * _DARKEN_STEP))
        if _contrast_ratio(candidate, _WHITE) >= _CONTRAST_FLOOR:
            return candidate
    return _BLACK


def normalize_accent_color(raw_color: str) -> str:
    """Return the canonical lowercase `#rrggbb` form of a merchant's accent.

    Accepts `#rgb` shorthand and any casing; rejects everything else as a
    field error so a malformed value never reaches the database check or, worse,
    ships to a public page as a broken CSS color.
    """
    if not isinstance(raw_color, str):
        raise LandingValidationError("accent_color", "Accent color must be a hex color.")

    text = raw_color.strip().lower()
    if not text:
        raise LandingValidationError("accent_color", "Accent color is required.")
    if not text.startswith("#"):
        text = f"#{text}"

    # Expand `#abc` before the pattern check so shorthand is stored canonically
    # rather than being rejected for a cosmetic difference.
    body = text[1:]
    if len(body) == 3 and all(char in "0123456789abcdef" for char in body):
        body = "".join(char * 2 for char in body)
        text = f"#{body}"

    if not _ACCENT_PATTERN.match(text):
        raise LandingValidationError(
            "accent_color",
            "Accent color must be a hex color such as #1a7a4c.",
        )
    return text


def derive_accent_palette(accent_color: str) -> AccentPalette:
    """Build the full chrome palette from one accent.

    The stored color is darkened first when it is too light to carry text (see
    `_ensure_readable_with_white_text`), so `accent` here is the color the page
    actually paints — the merchant's hue, at a lightness that stays legible.

    A stored value that cannot be parsed falls back to the default accent
    instead of raising: a public page rendering in the wrong green is a much
    smaller failure than a public page returning 500.
    """
    try:
        parse_hex(accent_color)
        raw = accent_color.strip().lower()
    except (AttributeError, ValueError):
        raw = DEFAULT_ACCENT_COLOR

    accent = _ensure_readable_with_white_text(raw)

    return AccentPalette(
        accent=accent,
        deep=blend_hex(accent, _BLACK, _DEEP_BLEND_WEIGHT),
        # Derived from the merchant's raw color, not the darkened one: this is a
        # background with no text of its own color on it, so it can keep the
        # hue exactly as picked.
        tint=blend_hex(raw, _WHITE, _TINT_BLEND_WEIGHT),
        ink=_INK_ON_ACCENT,
    )


def accent_hex_from_rgb(rgb: tuple[int, int, int]) -> str:
    """Format an RGB triple as a storable accent value."""
    return format_hex(rgb)
