"""BannerUploadService: the image pipeline's upload orchestration.

Composes `app.domains.images` (validation, EXIF stripping, variant
generation, edge-color extraction, opaque key generation) and
`app.domains.landings.banner_ordering`
with `R2Client` and the Prisma repositories.

Atomic completion (Requirements 4.11, 4.12): every required R2 object
(original + all variants) is uploaded before any database row is written;
the `image_assets` row, its `image_variants` rows, and the `banners` row
are created together in one Prisma transaction only after every upload
succeeds. On any failure — validation, opaque-key generation, or an R2
upload/outage — no database row is created and any R2 objects already
uploaded for this attempt are deleted, leaving no partial banner
association and no orphaned objects.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

from prisma import Prisma
from prisma.models import Banner

from app.db.repositories import (
    AuditLogRepository,
    BannerRepository,
    ImageAssetRepository,
    ImageVariantRepository,
    LandingRepository,
)
from app.domains.images.edge_color import EdgeColors, extract_edge_colors
from app.domains.images.errors import ImagePipelineUnavailableError
from app.domains.images.exif import strip_exif
from app.domains.images.opaque_key import generate_opaque_key
from app.domains.images.validation import validate_source_image
from app.domains.images.variants import GeneratedVariant, generate_variants
from app.domains.landings.alt_text import validate_alt_text
from app.domains.landings.banner_ordering import next_append_index, validate_can_add_banner
from app.domains.landings.errors import LandingNotFoundError
from app.storage.r2_client import R2Client, original_object_key, variant_object_key

_SOURCE_EXTENSION_BY_FORMAT = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
# Content types keyed by the lowercase format tag used both for the source
# extension (jpg/png/webp) and for GeneratedVariant.format (jpeg/webp).
_CONTENT_TYPE_BY_FORMAT = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


@dataclass(frozen=True)
class BannerUploadResult:
    banner: Banner
    image_asset_id: int


class BannerUploadService:
    def __init__(self, db: Prisma, r2: R2Client) -> None:
        self._db = db
        self._r2 = r2

    async def upload_banner(
        self, landing_id: int, *, raw_bytes: bytes, alt_text: str, actor: str
    ) -> BannerUploadResult:
        """Validate, process, and upload a new banner image for `landing_id`.

        Raises `LandingNotFoundError`, `ImageValidationError`,
        `OpaqueKeyGenerationError`, or `ImagePipelineUnavailableError` on
        failure; none of these leave a database row or an uploaded R2
        object behind.
        """
        landing = await LandingRepository(self._db).get_by_id(landing_id)
        if landing is None:
            raise LandingNotFoundError(landing_id)

        existing_banners = await BannerRepository(self._db).list_for_landing(landing_id)
        validate_can_add_banner(len(existing_banners), landing_id)

        alt_text = validate_alt_text(alt_text)

        validated = validate_source_image(raw_bytes)
        stripped_image = strip_exif(validated.image)
        variants = generate_variants(stripped_image)
        # Sampled from the same in-memory image as the variants, so the CTA
        # band colors cost one extra pass over two thin edge strips and are
        # never recomputed per request.
        edge_colors = extract_edge_colors(stripped_image)

        opaque_key = generate_opaque_key()  # raises OpaqueKeyGenerationError if both fail

        source_extension = _SOURCE_EXTENSION_BY_FORMAT[validated.format]
        source_key = original_object_key(opaque_key, source_extension)
        variant_keys: list[tuple[GeneratedVariant, str]] = [
            (variant, variant_object_key(opaque_key, variant.width, variant.format))
            for variant in variants
        ]

        uploaded_keys: list[str] = []
        try:
            await self._r2.put_bytes(
                source_key, raw_bytes, content_type=_CONTENT_TYPE_BY_FORMAT[source_extension]
            )
            uploaded_keys.append(source_key)
            for variant, key in variant_keys:
                await self._r2.put_bytes(
                    key, variant.data, content_type=_CONTENT_TYPE_BY_FORMAT[variant.format]
                )
                uploaded_keys.append(key)
        except Exception as exc:
            await self._cleanup_partial_upload(uploaded_keys)
            raise ImagePipelineUnavailableError() from exc

        try:
            return await self._persist(
                landing_id=landing_id,
                opaque_key=opaque_key,
                source_key=source_key,
                validated_width=validated.width,
                validated_height=validated.height,
                validated_format=validated.format.lower(),
                variant_keys=variant_keys,
                edge_colors=edge_colors,
                alt_text=alt_text,
                existing_banner_count=len(existing_banners),
                actor=actor,
            )
        except Exception:
            await self._cleanup_partial_upload(uploaded_keys)
            raise

    async def _persist(
        self,
        *,
        landing_id: int,
        opaque_key: str,
        source_key: str,
        validated_width: int,
        validated_height: int,
        validated_format: str,
        variant_keys: list[tuple[GeneratedVariant, str]],
        edge_colors: EdgeColors,
        alt_text: str,
        existing_banner_count: int,
        actor: str,
    ) -> BannerUploadResult:
        async with self._db.tx() as tx:
            image_assets = ImageAssetRepository(tx)
            image_variants = ImageVariantRepository(tx)
            banners = BannerRepository(tx)
            audit_log = AuditLogRepository(tx)

            asset = await image_assets.create(
                {
                    "opaqueKey": opaque_key,
                    "sourceObjectKey": source_key,
                    "sourceWidth": validated_width,
                    "sourceHeight": validated_height,
                    "sourceFormat": validated_format,
                    "status": "in_progress",
                    "topEdgeColor": edge_colors.top.color,
                    "bottomEdgeColor": edge_colors.bottom.color,
                    "topEdgeFlat": edge_colors.top.flat,
                    "bottomEdgeFlat": edge_colors.bottom.flat,
                }
            )

            for variant, key in variant_keys:
                await image_variants.create(
                    {
                        "imageAssetId": asset.id,
                        "width": variant.width,
                        "height": variant.height,
                        "format": variant.format,
                        "objectKey": key,
                        "version": opaque_key,
                    }
                )

            await image_assets.mark_complete(asset.id)

            banner = await banners.create(
                {
                    "landingId": landing_id,
                    "orderIndex": next_append_index(existing_banner_count),
                    "altText": alt_text,
                    "imageAssetId": asset.id,
                }
            )

            await audit_log.record(
                actor=actor,
                action="banner.upload",
                target_type="banner",
                target_id=str(banner.id),
                result="success",
            )

            return BannerUploadResult(banner=banner, image_asset_id=asset.id)

    async def _cleanup_partial_upload(self, uploaded_keys: list[str]) -> None:
        # Best-effort cleanup: the primary failure is already being raised
        # to the caller; a cleanup failure must not mask it or crash the
        # request.
        for key in uploaded_keys:
            with contextlib.suppress(Exception):
                await self._r2.delete(key)
