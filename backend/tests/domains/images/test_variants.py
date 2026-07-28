"""Unit + property tests for variant generation (Requirements 4.9, 4.10).

Required property (design.md -> Testing Strategy): for any supported
source dimensions, generated widths are from the configured set, are no
larger than the source, and preserve aspect ratio within encoding
tolerance.
"""

from __future__ import annotations

import io

from app.domains.images.variants import CONFIGURED_WIDTHS, VARIANT_FORMATS, generate_variants
from hypothesis import given, settings
from hypothesis import strategies as st
from PIL import Image


def _make_image(width: int, height: int) -> Image.Image:
    return Image.new("RGB", (width, height), color=(50, 100, 150))


class TestGenerateVariants:
    def test_generates_both_formats_for_every_width_that_fits(self) -> None:
        image = _make_image(1600, 900)

        variants = generate_variants(image)

        widths = {v.width for v in variants}
        assert widths == set(CONFIGURED_WIDTHS)
        for width in CONFIGURED_WIDTHS:
            formats_at_width = {v.format for v in variants if v.width == width}
            assert formats_at_width == set(VARIANT_FORMATS)

    def test_widths_greater_than_source_are_skipped(self) -> None:
        # Source width 600 is between the 480 and 768 configured widths.
        image = _make_image(600, 400)

        variants = generate_variants(image)

        widths = {v.width for v in variants}
        assert widths == {480}

    def test_source_narrower_than_smallest_configured_width_yields_no_variants(self) -> None:
        image = _make_image(480, 320)  # exactly the smallest configured width

        variants = generate_variants(image)

        assert {v.width for v in variants} == {480}

    def test_each_variant_is_a_decodable_image_of_the_stated_format(self) -> None:
        image = _make_image(1600, 1000)

        variants = generate_variants(image)

        for variant in variants:
            decoded = Image.open(io.BytesIO(variant.data))
            decoded.load()
            assert decoded.format == variant.format.upper()
            assert decoded.size == (variant.width, variant.height)

    def test_rgba_source_produces_a_valid_jpeg_variant(self) -> None:
        image = Image.new("RGBA", (600, 400), color=(10, 20, 30, 128))

        variants = generate_variants(image)

        jpeg_variants = [v for v in variants if v.format == "jpeg"]
        assert jpeg_variants
        for variant in jpeg_variants:
            decoded = Image.open(io.BytesIO(variant.data))
            decoded.load()
            assert decoded.mode == "RGB"


# --- Property test -------------------------------------------------------

_dimension_strategy = st.integers(min_value=480, max_value=4000)


@settings(deadline=2000)  # real image encode/decode per example is slower than hypothesis's default
@given(source_width=_dimension_strategy, source_height=_dimension_strategy)
def test_variant_widths_and_aspect_ratio_are_always_within_spec(
    source_width: int, source_height: int
) -> None:
    image = _make_image(source_width, source_height)

    variants = generate_variants(image)

    source_aspect = source_height / source_width
    for variant in variants:
        assert variant.width in CONFIGURED_WIDTHS
        assert variant.width <= source_width
        expected_height = round(variant.width * source_aspect)
        # Rounding tolerance: off-by-one is acceptable, more than that is not.
        assert abs(variant.height - expected_height) <= 1
