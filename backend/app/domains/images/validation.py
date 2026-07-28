"""Source-image validation (Requirements 4.1-4.6).

Validates by decoding the file — never trusting the client-supplied
extension or content-type header — before classifying it as a
Supported_Source_Image.
"""

from __future__ import annotations

import io

from app.domains.images.errors import ImageValidationError
from PIL import Image
from PIL import UnidentifiedImageError as PillowUnidentifiedImageError

ALLOWED_SOURCE_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})

SOURCE_WIDTH_MIN = 480
SOURCE_WIDTH_MAX = 8000
SOURCE_HEIGHT_MIN = 1
SOURCE_HEIGHT_MAX = 8000
SOURCE_MAX_TOTAL_PIXELS = 40_000_000
MIB = 1_048_576
SOURCE_MAX_BYTES = 10 * MIB


class ValidatedSourceImage:
    """A decoded, in-limits source image ready for EXIF stripping/variant
    generation. `format` is one of `ALLOWED_SOURCE_FORMATS` (uppercase)."""

    __slots__ = ("image", "format", "width", "height", "byte_size")

    def __init__(self, image: Image.Image, format_: str, width: int, height: int, byte_size: int):
        self.image = image
        self.format = format_
        self.width = width
        self.height = height
        self.byte_size = byte_size


def validate_source_image(raw_bytes: bytes) -> ValidatedSourceImage:
    """Decode and validate `raw_bytes` as a Supported_Source_Image.

    Raises `ImageValidationError` for every violation: undecodable data,
    disallowed format, out-of-range width/height, excess total pixels, or
    excess byte size (Requirement 4.6). Validation order follows the cheap
    checks first: byte size, then decode, then dimensions.
    """
    if len(raw_bytes) > SOURCE_MAX_BYTES:
        raise ImageValidationError(
            "file", f"File exceeds the maximum size of {SOURCE_MAX_BYTES} bytes (10 MiB)."
        )

    try:
        image = Image.open(io.BytesIO(raw_bytes))
        image.load()  # force full decode; confirms the file is genuinely this format
    except (PillowUnidentifiedImageError, OSError) as exc:
        raise ImageValidationError("file", "File could not be decoded as an image.") from exc

    image_format = image.format or ""
    if image_format not in ALLOWED_SOURCE_FORMATS:
        raise ImageValidationError(
            "file", f"Unsupported image format '{image_format}'. Allowed: JPEG, PNG, WebP."
        )

    width, height = image.size
    if not (SOURCE_WIDTH_MIN <= width <= SOURCE_WIDTH_MAX):
        raise ImageValidationError(
            "file", f"Width must be between {SOURCE_WIDTH_MIN} and {SOURCE_WIDTH_MAX} pixels."
        )
    if not (SOURCE_HEIGHT_MIN <= height <= SOURCE_HEIGHT_MAX):
        raise ImageValidationError(
            "file", f"Height must be between {SOURCE_HEIGHT_MIN} and {SOURCE_HEIGHT_MAX} pixels."
        )
    if width * height > SOURCE_MAX_TOTAL_PIXELS:
        raise ImageValidationError(
            "file", f"Total pixel count must not exceed {SOURCE_MAX_TOTAL_PIXELS}."
        )

    return ValidatedSourceImage(
        image=image, format_=image_format, width=width, height=height, byte_size=len(raw_bytes)
    )
