"""Upload lifecycle for 500×500 images attached to offers-price quantities."""

from __future__ import annotations

import asyncio
import contextlib

from PIL import ImageOps
from prisma import Prisma

from app.domains.images.errors import ImagePipelineUnavailableError
from app.domains.images.exif import strip_exif
from app.domains.images.offer_image import optimize_offer_image
from app.domains.images.opaque_key import generate_opaque_key
from app.domains.images.validation import validate_source_image
from app.domains.landings.errors import LandingNotFoundError, LandingValidationError
from app.storage.r2_client import (
    R2Client,
    offer_image_object_key,
    original_object_key,
)

_SOURCE_EXTENSION_BY_FORMAT = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
_SOURCE_CONTENT_TYPE = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


class OfferImageNotFoundError(LandingValidationError):
    def __init__(self) -> None:
        super().__init__("quantity", "Offer image not found.")


class OfferImageUploadService:
    def __init__(self, db: Prisma, r2: R2Client) -> None:
        self._db = db
        self._r2 = r2

    async def upload(
        self,
        landing_id: int,
        block_id: int,
        quantity: int,
        *,
        raw_bytes: bytes,
        actor: str,
    ) -> None:
        block = await self._db.landingblock.find_first(
            where={"id": block_id, "landingId": landing_id}
        )
        if block is None:
            raise LandingNotFoundError(landing_id)
        if block.blockType != "offers_price":
            raise LandingValidationError("block_id", "El componente no es de ofertas y precios.")

        landing = await self._db.landing.find_unique(where={"id": landing_id})
        if landing is None:
            raise LandingNotFoundError(landing_id)
        if isinstance(quantity, bool) or quantity < 1 or quantity > landing.offerCount:
            raise LandingValidationError(
                "quantity", "La imagen debe pertenecer a una oferta visible de la landing."
            )

        validated = validate_source_image(raw_bytes)
        # Apply camera orientation before discarding EXIF so phone uploads are
        # cropped from the same upright image the merchant selected.
        clean_image = strip_exif(ImageOps.exif_transpose(validated.image))
        optimized = await asyncio.to_thread(optimize_offer_image, clean_image)
        opaque_key = generate_opaque_key()
        source_extension = _SOURCE_EXTENSION_BY_FORMAT[validated.format]
        source_key = original_object_key(opaque_key, source_extension)
        image_key = offer_image_object_key(opaque_key)
        existing = await self._db.offerimageasset.find_first(
            where={"landingBlockId": block_id, "quantity": quantity}
        )

        uploaded: list[str] = []
        try:
            await self._r2.put_bytes(
                source_key,
                raw_bytes,
                content_type=_SOURCE_CONTENT_TYPE[source_extension],
            )
            uploaded.append(source_key)
            await self._r2.put_bytes(image_key, optimized.data, content_type="image/webp")
            uploaded.append(image_key)

            async with self._db.tx() as tx:
                data = {
                    "opaqueKey": opaque_key,
                    "sourceObjectKey": source_key,
                    "imageObjectKey": image_key,
                    "width": optimized.width,
                    "height": optimized.height,
                    "byteSize": len(optimized.data),
                }
                if existing is None:
                    stored = await tx.offerimageasset.create(
                        data={"landingBlockId": block_id, "quantity": quantity, **data}
                    )
                else:
                    stored = await tx.offerimageasset.update(
                        where={"id": existing.id}, data=data
                    )
                await tx.auditlog.create(
                    data={
                        "actor": actor,
                        "action": "offer_image.upload",
                        "targetType": "offer_image_asset",
                        "targetId": str(stored.id),
                        "result": "success",
                    }
                )
        except (LandingNotFoundError, LandingValidationError):
            raise
        except Exception as exc:
            await self._cleanup(uploaded)
            raise ImagePipelineUnavailableError() from exc

        if existing is not None:
            await self._cleanup([existing.sourceObjectKey, existing.imageObjectKey])

    async def delete(
        self, landing_id: int, block_id: int, quantity: int, *, actor: str
    ) -> None:
        block = await self._db.landingblock.find_first(
            where={"id": block_id, "landingId": landing_id}
        )
        if block is None:
            raise LandingNotFoundError(landing_id)
        asset = await self._db.offerimageasset.find_first(
            where={"landingBlockId": block_id, "quantity": quantity}
        )
        if asset is None:
            raise OfferImageNotFoundError()

        async with self._db.tx() as tx:
            await tx.offerimageasset.delete(where={"id": asset.id})
            await tx.auditlog.create(
                data={
                    "actor": actor,
                    "action": "offer_image.delete",
                    "targetType": "offer_image_asset",
                    "targetId": str(asset.id),
                    "result": "success",
                }
            )
        await self._cleanup([asset.sourceObjectKey, asset.imageObjectKey])

    async def _cleanup(self, keys: list[str]) -> None:
        for key in keys:
            with contextlib.suppress(Exception):
                await self._r2.delete(key)
