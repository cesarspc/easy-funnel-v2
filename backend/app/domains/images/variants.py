"""Responsive image variant generation (Requirements 4.9, 4.10).

Generates WebP + JPEG variants at the configured widths, skipping any
width greater than the source, and preserving aspect ratio within
image-encoding rounding tolerance.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image

CONFIGURED_WIDTHS = (480, 768, 1200, 1600)
VARIANT_FORMATS = ("webp", "jpeg")

_WEBP_QUALITY = 82
_JPEG_QUALITY = 85


@dataclass(frozen=True)
class GeneratedVariant:
    width: int
    height: int
    format: str  # "webp" | "jpeg"
    data: bytes


def _target_height(source_width: int, source_height: int, target_width: int) -> int:
    """Compute the aspect-preserving height for `target_width`."""
    return round(target_width * source_height / source_width)


def generate_variants(image: Image.Image) -> list[GeneratedVariant]:
    """Generate every configured-width x format variant that fits the source.

    Widths greater than the source width are skipped entirely (never
    upscaled). RGBA source images generating a JPEG variant are flattened
    onto white (JPEG has no alpha channel).
    """
    source_width, source_height = image.size
    variants: list[GeneratedVariant] = []

    for width in CONFIGURED_WIDTHS:
        if width > source_width:
            continue
        height = _target_height(source_width, source_height, width)
        resized = image.resize((width, height))

        for fmt in VARIANT_FORMATS:
            buf = io.BytesIO()
            if fmt == "webp":
                resized.save(buf, format="WEBP", quality=_WEBP_QUALITY)
            else:
                to_encode = resized.convert("RGB") if resized.mode == "RGBA" else resized
                to_encode.save(buf, format="JPEG", quality=_JPEG_QUALITY)
            variants.append(
                GeneratedVariant(width=width, height=height, format=fmt, data=buf.getvalue())
            )

    return variants
