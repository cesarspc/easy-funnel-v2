"""Unit tests for EXIF stripping (Requirement 4.8)."""

from __future__ import annotations

import io

from app.domains.images.exif import strip_exif
from PIL import Image


def _jpeg_with_exif() -> Image.Image:
    image = Image.new("RGB", (100, 80), color=(10, 20, 30))
    exif = image.getexif()
    exif[0x0110] = "TestCameraModel"  # Model tag
    buf = io.BytesIO()
    image.save(buf, format="JPEG", exif=exif)
    reopened = Image.open(io.BytesIO(buf.getvalue()))
    reopened.load()
    return reopened


class TestStripExif:
    def test_source_has_exif_before_stripping(self) -> None:
        source = _jpeg_with_exif()
        assert dict(source.getexif()) != {}

    def test_stripped_image_carries_no_exif(self) -> None:
        source = _jpeg_with_exif()

        stripped = strip_exif(source)

        assert dict(stripped.getexif()) == {}

    def test_stripping_preserves_pixel_dimensions(self) -> None:
        source = _jpeg_with_exif()

        stripped = strip_exif(source)

        assert stripped.size == source.size

    def test_re_saving_the_stripped_image_still_carries_no_exif(self) -> None:
        # Proves the EXIF-free guarantee survives a subsequent save/reload,
        # which is what the variant-generation pipeline actually does.
        source = _jpeg_with_exif()
        stripped = strip_exif(source)

        buf = io.BytesIO()
        stripped.save(buf, format="JPEG")
        reloaded = Image.open(io.BytesIO(buf.getvalue()))
        reloaded.load()

        assert dict(reloaded.getexif()) == {}
