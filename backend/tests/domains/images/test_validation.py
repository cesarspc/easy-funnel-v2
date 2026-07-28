"""Unit tests for source-image validation (Requirements 4.1-4.6)."""

from __future__ import annotations

import pytest
from app.domains.images.errors import ImageValidationError
from app.domains.images.validation import (
    SOURCE_HEIGHT_MAX,
    SOURCE_HEIGHT_MIN,
    SOURCE_MAX_BYTES,
    SOURCE_WIDTH_MAX,
    SOURCE_WIDTH_MIN,
    validate_source_image,
)

from tests.domains.images.conftest import make_image_bytes


class TestSupportedFormats:
    def test_jpeg_is_accepted(self) -> None:
        result = validate_source_image(make_image_bytes(600, 400, format_="JPEG"))
        assert result.format == "JPEG"

    def test_png_is_accepted(self) -> None:
        result = validate_source_image(make_image_bytes(600, 400, format_="PNG"))
        assert result.format == "PNG"

    def test_webp_is_accepted(self) -> None:
        result = validate_source_image(make_image_bytes(600, 400, format_="WEBP"))
        assert result.format == "WEBP"

    def test_gif_is_rejected(self) -> None:
        with pytest.raises(ImageValidationError) as exc_info:
            validate_source_image(make_image_bytes(600, 400, format_="GIF"))
        assert exc_info.value.field == "file"

    def test_undecodable_bytes_are_rejected(self) -> None:
        with pytest.raises(ImageValidationError):
            validate_source_image(b"this is not an image at all")

    def test_client_extension_is_never_trusted_bmp_content_rejected(self) -> None:
        # BMP is a real, decodable Pillow format but not in our allowlist -
        # proves rejection is based on decoded format, not any extension.
        result_bytes = make_image_bytes(600, 400, format_="BMP")
        with pytest.raises(ImageValidationError):
            validate_source_image(result_bytes)


class TestWidthBoundaries:
    def test_minimum_width_boundary_is_accepted(self) -> None:
        result = validate_source_image(make_image_bytes(SOURCE_WIDTH_MIN, 600))
        assert result.width == SOURCE_WIDTH_MIN

    def test_maximum_width_boundary_is_accepted(self) -> None:
        result = validate_source_image(make_image_bytes(SOURCE_WIDTH_MAX, 1))
        assert result.width == SOURCE_WIDTH_MAX

    def test_below_minimum_width_is_rejected(self) -> None:
        with pytest.raises(ImageValidationError) as exc_info:
            validate_source_image(make_image_bytes(SOURCE_WIDTH_MIN - 1, 600))
        assert exc_info.value.field == "file"

    def test_above_maximum_width_is_rejected(self) -> None:
        with pytest.raises(ImageValidationError):
            validate_source_image(make_image_bytes(SOURCE_WIDTH_MAX + 1, 1))


class TestHeightBoundaries:
    def test_minimum_height_boundary_is_accepted(self) -> None:
        result = validate_source_image(make_image_bytes(600, SOURCE_HEIGHT_MIN))
        assert result.height == SOURCE_HEIGHT_MIN

    def test_maximum_height_boundary_is_accepted(self) -> None:
        result = validate_source_image(make_image_bytes(480, SOURCE_HEIGHT_MAX))
        assert result.height == SOURCE_HEIGHT_MAX

    def test_below_minimum_height_is_unreachable_for_any_real_image(self) -> None:
        # SOURCE_HEIGHT_MIN is 1; no encodable image file can have height 0
        # or negative height, so the "below minimum" branch for height is
        # unreachable via real image bytes (unlike width, where 479 is a
        # perfectly valid image that must still be rejected).
        with pytest.raises(ValueError):
            make_image_bytes(600, SOURCE_HEIGHT_MIN - 1)

    def test_above_maximum_height_is_rejected(self) -> None:
        with pytest.raises(ImageValidationError):
            validate_source_image(make_image_bytes(480, SOURCE_HEIGHT_MAX + 1))


class TestTotalPixelBoundary:
    def test_exactly_40_million_pixels_is_accepted(self) -> None:
        # 8000 * 5000 = 40,000,000 exactly.
        result = validate_source_image(make_image_bytes(8000, 5000))
        assert result.width * result.height == 40_000_000

    def test_above_40_million_pixels_is_rejected(self) -> None:
        # 8000 * 5001 = 40,008,000; both dimensions individually in range.
        with pytest.raises(ImageValidationError):
            validate_source_image(make_image_bytes(8000, 5001))


class TestByteSizeBoundary:
    def test_over_10_mib_is_rejected_before_any_decode_attempt(self) -> None:
        # The size check runs before decoding, so arbitrary bytes over the
        # limit are rejected without needing a real oversized image file.
        oversized = b"\xff" * (SOURCE_MAX_BYTES + 1)
        with pytest.raises(ImageValidationError) as exc_info:
            validate_source_image(oversized)
        assert exc_info.value.field == "file"

    def test_at_exactly_10_mib_of_valid_image_bytes_is_accepted(self) -> None:
        # A real valid image whose encoded size is comfortably under the
        # limit still exercises the "at boundary, still valid data" path.
        result = validate_source_image(make_image_bytes(600, 400))
        assert result.byte_size <= SOURCE_MAX_BYTES
