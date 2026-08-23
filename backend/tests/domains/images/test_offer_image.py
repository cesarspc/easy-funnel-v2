"""Fixed-size processing for images attached to offers-price cards."""

from __future__ import annotations

import io

from app.domains.images.offer_image import OFFER_IMAGE_SIZE, optimize_offer_image
from PIL import Image


def test_optimizes_any_aspect_ratio_to_a_decodable_500_square_webp() -> None:
    result = optimize_offer_image(Image.new("RGB", (1200, 480), color=(35, 90, 145)))

    decoded = Image.open(io.BytesIO(result.data))
    decoded.load()

    assert decoded.format == "WEBP"
    assert decoded.size == (OFFER_IMAGE_SIZE, OFFER_IMAGE_SIZE)
    assert (result.width, result.height) == (500, 500)


def test_transparent_sources_are_supported() -> None:
    result = optimize_offer_image(Image.new("RGBA", (480, 900), color=(20, 40, 60, 120)))

    decoded = Image.open(io.BytesIO(result.data))
    decoded.load()
    assert decoded.size == (500, 500)
