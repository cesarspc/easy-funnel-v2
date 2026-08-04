"""Unit + property tests for the per-landing accent color and its palette.

Covers `app.domains.landings.accent_color`. Two things matter here:

- **Normalization is the gate.** Whatever a merchant pastes has to come out as
  the canonical lowercase `#rrggbb` the `landings_accent_color_format` database
  check expects, or be rejected as a field error. Nothing malformed may reach
  the column or a public page's `style` attribute.
- **The derived palette must stay readable.** `ink` is chosen against `accent`,
  so the property that actually protects buyers is that the pair always clears
  the WCAG contrast floor for text — for every possible accent, not just the
  default green.
"""

from __future__ import annotations

import pytest
from app.domains.images.edge_color import parse_hex, relative_luminance
from app.domains.landings.accent_color import (
    DEFAULT_ACCENT_COLOR,
    derive_accent_palette,
    normalize_accent_color,
)
from app.domains.landings.errors import LandingValidationError
from hypothesis import given
from hypothesis import strategies as st

#: WCAG 2.x contrast floor for normal-size body text.
_CONTRAST_FLOOR = 4.5

_HEX_BYTES = st.integers(min_value=0, max_value=255)


def _contrast(first: str, second: str) -> float:
    first_luminance = relative_luminance(first)
    second_luminance = relative_luminance(second)
    lighter, darker = (
        (first_luminance, second_luminance)
        if first_luminance > second_luminance
        else (second_luminance, first_luminance)
    )
    return (lighter + 0.05) / (darker + 0.05)


class TestNormalizeAccentColor:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("#1a7a4c", "#1a7a4c"),
            ("#1A7A4C", "#1a7a4c"),
            ("  #1a7a4c  ", "#1a7a4c"),
            # A brand hex is often pasted without the leading '#'.
            ("1a7a4c", "#1a7a4c"),
            # Shorthand is expanded rather than rejected for a cosmetic reason.
            ("#abc", "#aabbcc"),
            ("#ABC", "#aabbcc"),
            ("abc", "#aabbcc"),
        ],
    )
    def test_accepted_inputs_are_canonicalized(self, raw: str, expected: str) -> None:
        assert normalize_accent_color(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "   ",
            "nope",
            "#12345",
            "#1234567",
            "#gggggg",
            "rgb(1,2,3)",
            "red",
            # A CSS injection attempt must be a field error, never a stored value.
            "#000; background: url(evil)",
        ],
    )
    def test_malformed_input_is_a_field_specific_error(self, raw: str) -> None:
        with pytest.raises(LandingValidationError) as exc_info:
            normalize_accent_color(raw)
        assert exc_info.value.field == "accent_color"

    def test_non_string_input_is_rejected(self) -> None:
        with pytest.raises(LandingValidationError) as exc_info:
            normalize_accent_color(None)  # type: ignore[arg-type]
        assert exc_info.value.field == "accent_color"

    @given(st.text())
    def test_never_returns_a_value_the_database_check_would_reject(self, raw: str) -> None:
        try:
            result = normalize_accent_color(raw)
        except LandingValidationError:
            return
        assert len(result) == 7
        assert result.startswith("#")
        assert result == result.lower()
        # Parsing is what the public page ultimately depends on.
        parse_hex(result)


class TestDeriveAccentPalette:
    def test_default_accent_produces_the_shipped_greens(self) -> None:
        palette = derive_accent_palette(DEFAULT_ACCENT_COLOR)
        assert palette.accent == DEFAULT_ACCENT_COLOR
        # Deep is a darker version of the accent, not an unrelated color.
        assert relative_luminance(palette.deep) < relative_luminance(palette.accent)
        # Tint is a near-white wash, so it can sit behind body text.
        assert relative_luminance(palette.tint) > relative_luminance(palette.accent)

    def test_a_light_accent_is_darkened_rather_than_given_dark_text(self) -> None:
        # The whole reason lightness is derived rather than trusted: a merchant
        # picking a bright yellow cannot be allowed to ship a button whose label
        # is unreadable. The hue survives, the lightness moves.
        palette = derive_accent_palette("#ffe000")
        assert palette.ink == "#ffffff"
        assert relative_luminance(palette.accent) < relative_luminance("#ffe000")
        assert _contrast(palette.accent, palette.ink) >= _CONTRAST_FLOOR

    def test_an_already_dark_accent_is_left_alone(self) -> None:
        # Nothing is "corrected" that already works, so a merchant who picked a
        # deep brand color sees exactly that color on the page.
        assert derive_accent_palette("#10361f").accent == "#10361f"

    def test_a_mid_tone_accent_is_darkened_until_its_label_is_readable(self) -> None:
        # The case the property test originally caught: neither white nor
        # near-black text clears 4.5:1 on a medium purple, so the background is
        # what has to move.
        palette = derive_accent_palette("#a05e9d")
        assert _contrast(palette.accent, palette.ink) >= _CONTRAST_FLOOR

    @pytest.mark.parametrize("broken", ["", "not-a-color", "#xyzxyz"])
    def test_unparseable_stored_value_falls_back_instead_of_raising(self, broken: str) -> None:
        # A public page rendering in the default green is a far smaller failure
        # than a public page returning 500.
        assert derive_accent_palette(broken).accent == DEFAULT_ACCENT_COLOR

    @given(_HEX_BYTES, _HEX_BYTES, _HEX_BYTES)
    def test_ink_always_clears_the_contrast_floor_on_the_accent(
        self, red: int, green: int, blue: int
    ) -> None:
        accent = f"#{red:02x}{green:02x}{blue:02x}"
        palette = derive_accent_palette(accent)
        assert _contrast(palette.accent, palette.ink) >= _CONTRAST_FLOOR

    @given(_HEX_BYTES, _HEX_BYTES, _HEX_BYTES)
    def test_accent_is_always_usable_as_text_on_the_pages_white_surface(
        self, red: int, green: int, blue: int
    ) -> None:
        # The accent is used as a text color too (the saving line, accent copy),
        # so it has to clear the floor against white as well as carry white text.
        palette = derive_accent_palette(f"#{red:02x}{green:02x}{blue:02x}")
        assert _contrast(palette.accent, "#ffffff") >= _CONTRAST_FLOOR

    @given(_HEX_BYTES, _HEX_BYTES, _HEX_BYTES)
    def test_hover_shade_stays_readable_too(self, red: int, green: int, blue: int) -> None:
        # `deep` only ever darkens the (already passing) accent, so the button
        # label cannot become unreadable on hover.
        palette = derive_accent_palette(f"#{red:02x}{green:02x}{blue:02x}")
        assert _contrast(palette.deep, palette.ink) >= _CONTRAST_FLOOR

    @given(_HEX_BYTES, _HEX_BYTES, _HEX_BYTES)
    def test_every_derived_shade_is_a_usable_css_color(
        self, red: int, green: int, blue: int
    ) -> None:
        palette = derive_accent_palette(f"#{red:02x}{green:02x}{blue:02x}")
        for shade in (palette.accent, palette.deep, palette.tint, palette.ink):
            assert len(shade) == 7
            parse_hex(shade)

    @given(_HEX_BYTES, _HEX_BYTES, _HEX_BYTES)
    def test_tint_stays_light_enough_to_carry_body_text(
        self, red: int, green: int, blue: int
    ) -> None:
        # The tint is the background of an offer tile whose label is Ink, so it
        # has to stay near-white for every accent, including black.
        palette = derive_accent_palette(f"#{red:02x}{green:02x}{blue:02x}")
        assert _contrast(palette.tint, "#14181c") >= _CONTRAST_FLOOR
