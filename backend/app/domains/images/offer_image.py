"""Fixed 500×500 image optimization for one offers-price card."""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageOps

OFFER_IMAGE_SIZE = 500
_WEBP_QUALITY = 82


@dataclass(frozen=True)
class OptimizedOfferImage:
    data: bytes
    width: int = OFFER_IMAGE_SIZE
    height: int = OFFER_IMAGE_SIZE


def optimize_offer_image(image: Image.Image) -> OptimizedOfferImage:
    """Center-crop any validated aspect ratio and encode one 500×500 WebP."""
    fitted = ImageOps.fit(
        image,
        (OFFER_IMAGE_SIZE, OFFER_IMAGE_SIZE),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )
    output = io.BytesIO()
    fitted.save(output, format="WEBP", quality=_WEBP_QUALITY, method=6)
    return OptimizedOfferImage(data=output.getvalue())
