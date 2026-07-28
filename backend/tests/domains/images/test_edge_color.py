"""Unit + property tests for banner edge-color extraction and color math.

Covers `app.domains.images.edge_color`: the precomputed top/bottom edge
colors persisted at upload, the flatness signal that guards against
representing a busy edge with one color, and the sRGB/linear-light helpers
the CTA band derivation builds on.
"""

from __future__ import annotations

import pytest
from app.domains.images.edge_color import (
    EDGE_FLATNESS_MAX_STDDEV,
    EDGE_STRIP_FRACTION,
    EDGE_STRIP_MAX_PX,
    FOREGROUND_DARK,
    FOREGROUND_LIGHT,
    blend_hex,
    edge_strip_height,
    extract_edge_colors,
    format_hex,
    parse_hex,
    preferred_foreground,
    relative_luminance,
)
from hypothesis import given, settings
from hypothesis import strategies as st
from PIL import Image

_CHANNEL = st.integers(min_value=0, max_value=255)
_RGB = st.tuples(_CHANNEL, _CHANNEL, _CHANNEL)


def _solid(width: int, height: int, color: tuple[int, int, int]) -> Image.Image:
    return Image.new("RGB", (width, height), color=color)


def _two_band(
    width: int,
    height: int,
    top_color: tuple[int, int, int],
    bottom_color: tuple[int, int, int],
) -> Image.Image:
    """An image whose top half is `top_color` and bottom half `bottom_color`."""
    image = Image.new("RGB", (width, height), color=top_color)
    image.paste(
        Image.new("RGB", (width, height - height // 2), color=bottom_color),
        (0, height // 2),
    )
    return image


class TestFormatAndParseHex:
    def test_format_is_lowercase_six_digit(self) -> None:
        assert format_hex((0, 128, 255)) == "#0080ff"

    def test_parses_shorthand(self) -> None:
        assert parse_hex("#0af") == (0x00, 0xAA, 0xFF)

    @pytest.mark.parametrize("value", ["", "#", "#12", "#12345", "#1234567", "#gggggg", "not"])
    def test_rejects_malformed_values(self, value: str) -> None:
        with pytest.raises(ValueError):
            parse_hex(value)

    @given(rgb=_RGB)
    def test_format_parse_round_trips(self, rgb: tuple[int, int, int]) -> None:
        assert parse_hex(format_hex(rgb)) == rgb


class TestBlendHex:
    def test_weight_zero_and_one_return_the_endpoints(self) -> None:
        assert blend_hex("#000000", "#ffffff", 0.0) == "#000000"
        assert blend_hex("#000000", "#ffffff", 1.0) == "#ffffff"

    def test_midpoint_is_symmetric(self) -> None:
        assert blend_hex("#204080", "#c0a060") == blend_hex("#c0a060", "#204080")

    def test_identical_colors_blend_to_themselves(self) -> None:
        assert blend_hex("#3c6e91", "#3c6e91") == "#3c6e91"

    def test_black_white_midpoint_is_linear_light_not_byte_average(self) -> None:
        # A byte-space average would give #808080 (luminance ~0.216); the
        # linear-light midpoint is the perceptually lighter #bcbcbc.
        assert blend_hex("#000000", "#ffffff") == "#bcbcbc"

    @pytest.mark.parametrize("weight", [-0.01, 1.01])
    def test_rejects_out_of_range_weight(self, weight: float) -> None:
        with pytest.raises(ValueError):
            blend_hex("#000000", "#ffffff", weight)

    @given(first=_RGB, second=_RGB)
    @settings(max_examples=60, deadline=None)
    def test_blend_luminance_lies_between_the_endpoints(
        self, first: tuple[int, int, int], second: tuple[int, int, int]
    ) -> None:
        first_hex, second_hex = format_hex(first), format_hex(second)
        blended = relative_luminance(blend_hex(first_hex, second_hex))
        low, high = sorted((relative_luminance(first_hex), relative_luminance(second_hex)))
        # 1/255 of tolerance absorbs the 8-bit re-quantization of the result.
        assert low - 0.005 <= blended <= high + 0.005


class TestLuminanceAndForeground:
    def test_black_and_white_bounds(self) -> None:
        assert relative_luminance("#000000") == pytest.approx(0.0)
        assert relative_luminance("#ffffff") == pytest.approx(1.0)

    def test_light_background_prefers_dark_foreground(self) -> None:
        assert preferred_foreground("#ffffff") == FOREGROUND_DARK
        assert preferred_foreground("#f2e9dd") == FOREGROUND_DARK

    def test_dark_background_prefers_light_foreground(self) -> None:
        assert preferred_foreground("#000000") == FOREGROUND_LIGHT
        assert preferred_foreground("#1b2a3a") == FOREGROUND_LIGHT


class TestEdgeStripHeight:
    def test_uses_the_configured_fraction(self) -> None:
        assert edge_strip_height(1000) == round(1000 * EDGE_STRIP_FRACTION)

    def test_clamps_to_at_least_one_row(self) -> None:
        assert edge_strip_height(1) == 1
        assert edge_strip_height(10) == 1

    def test_clamps_to_the_absolute_cap(self) -> None:
        # The CTA sits flush against the edge, so a tall source must not turn
        # the sample into a whole-region average.
        assert edge_strip_height(8000) == EDGE_STRIP_MAX_PX

    def test_rejects_non_positive_height(self) -> None:
        with pytest.raises(ValueError):
            edge_strip_height(0)


class TestExtractEdgeColors:
    def test_solid_image_yields_that_color_on_both_edges(self) -> None:
        edges = extract_edge_colors(_solid(600, 400, (60, 120, 180)))

        assert edges.top.color == "#3c78b4"
        assert edges.bottom.color == "#3c78b4"
        assert edges.top.flat and edges.bottom.flat
        assert edges.top.stddev == pytest.approx(0.0)

    def test_two_band_image_samples_each_edge_independently(self) -> None:
        edges = extract_edge_colors(_two_band(600, 400, (255, 0, 0), (0, 0, 255)))

        assert edges.top.color == "#ff0000"
        assert edges.bottom.color == "#0000ff"
        assert edges.top.flat and edges.bottom.flat

    def test_busy_edge_is_reported_as_not_flat(self) -> None:
        # Alternating black/white columns across the full height: the mean is
        # meaningless as a band color, and the stddev must say so.
        image = Image.new("RGB", (600, 400), color=(0, 0, 0))
        for x in range(0, 600, 2):
            image.paste(Image.new("RGB", (1, 400), color=(255, 255, 255)), (x, 0))

        edges = extract_edge_colors(image)

        assert not edges.top.flat
        assert not edges.bottom.flat
        assert edges.top.stddev > EDGE_FLATNESS_MAX_STDDEV

    def test_subtle_gradient_edge_stays_flat(self) -> None:
        # A gentle vertical gradient over the sampled strip is still faithfully
        # representable by one color.
        height = 400
        image = Image.new("RGB", (600, height))
        for y in range(height):
            value = 100 + int(40 * y / height)
            image.paste(Image.new("RGB", (600, 1), color=(value, value, value)), (0, y))

        edges = extract_edge_colors(image)

        assert edges.top.flat
        assert edges.bottom.flat

    def test_transparent_edge_is_flattened_over_white(self) -> None:
        image = Image.new("RGBA", (600, 400), color=(0, 0, 0, 0))

        edges = extract_edge_colors(image)

        assert edges.top.color == "#ffffff"
        assert edges.bottom.color == "#ffffff"

    def test_palette_image_is_supported(self) -> None:
        image = _solid(600, 400, (10, 200, 90)).convert("P", dither=Image.Dither.NONE)

        edges = extract_edge_colors(image)

        # The default P conversion snaps to a 6x6x6-ish web palette, so assert
        # the sampled edge lands within one palette step of the source color.
        for channel, expected in zip(parse_hex(edges.top.color), (10, 200, 90), strict=True):
            assert abs(channel - expected) <= 51
        assert edges.top.flat and edges.bottom.flat

    def test_dithered_palette_edge_is_reported_as_not_flat(self) -> None:
        # Documented trade-off: dithering scatters pixel values, so the strip
        # is measured as busy and the band falls back to the neutral rather
        # than trusting an average of the dither pattern.
        image = _solid(600, 400, (10, 200, 90)).convert("P", dither=Image.Dither.FLOYDSTEINBERG)

        edges = extract_edge_colors(image)

        assert not edges.top.flat

    def test_single_row_image_samples_the_same_row_twice(self) -> None:
        edges = extract_edge_colors(_solid(480, 1, (12, 34, 56)))

        assert edges.top.color == edges.bottom.color == "#0c2238"

    @given(
        width=st.integers(min_value=1, max_value=200),
        height=st.integers(min_value=1, max_value=200),
        rgb=_RGB,
    )
    @settings(max_examples=40, deadline=None)
    def test_solid_color_extraction_is_exact_at_any_size(
        self, width: int, height: int, rgb: tuple[int, int, int]
    ) -> None:
        """For any solid source, both edges are exactly that color and flat.

        The linear-light average of a constant strip must survive the
        de-gamma/re-gamma round trip without drift.
        """
        edges = extract_edge_colors(_solid(width, height, rgb))

        assert parse_hex(edges.top.color) == rgb
        assert parse_hex(edges.bottom.color) == rgb
        assert edges.top.flat and edges.bottom.flat
