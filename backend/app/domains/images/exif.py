"""EXIF stripping (Requirement 4.8).

Device/timestamp/location metadata must never reach a public variant.
Pillow does not carry EXIF into a re-save unless it is explicitly passed
back via the `exif=` save kwarg, so simply not doing so strips it.
"""

from __future__ import annotations

from PIL import Image


def strip_exif(image: Image.Image) -> Image.Image:
    """Return a copy of `image` guaranteed to carry no EXIF metadata.

    Rebuilds a fresh `Image` from the raw pixel buffer (rather than relying
    on "just don't pass exif= on save") so the guarantee holds regardless
    of what a later save call in the pipeline does.
    """
    return Image.frombytes(image.mode, image.size, image.tobytes())
