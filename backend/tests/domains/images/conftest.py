"""Shared image-fixture helpers for the image pipeline domain tests."""

from __future__ import annotations

import io

from PIL import Image


def make_image_bytes(
    width: int, height: int, *, format_: str = "JPEG", color: tuple[int, int, int] = (255, 0, 0)
) -> bytes:
    """Build an in-memory encoded image of the given size/format for tests."""
    image = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    save_kwargs = {}
    if format_ == "JPEG":
        save_kwargs["quality"] = 50  # keep fixture bytes small
    image.save(buf, format=format_, **save_kwargs)
    return buf.getvalue()
