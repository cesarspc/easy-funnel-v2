"""Create an active product and published landing from one saved template.

Source media is staged by the caller below the configured R2 ``originals/``
prefix.  This service reads those objects through the private R2 client and
passes their bytes through the same domain pipelines as dashboard uploads.
All generated objects are written under fresh opaque keys.  Only after every
file has validated, transformed and uploaded does one Prisma transaction
create the product, landing, banners, blocks and block assets and publish the
result.  A failed preparation or transaction removes every newly generated R2
object and never modifies the supplied originals.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Any, cast

from PIL import ImageOps
from prisma import Json, Prisma

from app.domains.images.edge_color import EdgeColors, extract_edge_colors
from app.domains.images.errors import ImagePipelineUnavailableError
from app.domains.images.exif import strip_exif
from app.domains.images.offer_image import OptimizedOfferImage, optimize_offer_image
from app.domains.images.opaque_key import generate_opaque_key
from app.domains.images.validation import validate_source_image
from app.domains.images.variants import generate_variants
from app.domains.landings.alt_text import validate_alt_text
from app.domains.landings.errors import DuplicateSlugError, LandingValidationError
from app.domains.landings.template_instantiation import (
    TemplateMediaRequirement,
    describe_media_requirements,
    r2_original_object_key,
    validate_block_asset_assignments,
)
from app.domains.landings.templates import parse_template_blocks, parse_template_config
from app.domains.products.errors import DuplicateSkuError
from app.domains.products.validation import (
    validate_description,
    validate_name,
    validate_price,
    validate_sku,
)
from app.domains.products.variants import validate_variant_options
from app.domains.videos import OptimizedVideo, VideoPipelineError, optimize_video
from app.services.landing_template_service import TemplateNotFoundError
from app.storage.r2_client import (
    R2Client,
    offer_image_object_key,
    original_object_key,
    variant_object_key,
    video_object_key,
    video_poster_object_key,
)

_SOURCE_EXTENSION_BY_FORMAT = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
_CONTENT_TYPE_BY_EXTENSION = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


class TemplateVersionConflictError(Exception):
    """The template changed after the caller obtained its creation contract."""


class R2OriginalNotFoundError(LandingValidationError):
    def __init__(self, public_url: str) -> None:
        super().__init__("original_url", f"No existe el original de R2: {public_url}")


@dataclass(frozen=True)
class PreparedImageVariant:
    width: int
    height: int
    format: str
    object_key: str


@dataclass(frozen=True)
class PreparedBanner:
    alt_text: str
    opaque_key: str
    source_key: str
    source_width: int
    source_height: int
    source_format: str
    variants: tuple[PreparedImageVariant, ...]
    edges: EdgeColors


@dataclass(frozen=True)
class PreparedOfferImage:
    quantity: int
    opaque_key: str
    source_key: str
    image_key: str
    optimized: OptimizedOfferImage


@dataclass(frozen=True)
class PreparedVideo:
    caption: str | None
    opaque_key: str
    video_key: str
    poster_key: str
    optimized: OptimizedVideo


@dataclass(frozen=True)
class PreparedBlockMedia:
    videos: tuple[PreparedVideo, ...] = ()
    offer_images: tuple[PreparedOfferImage, ...] = ()


@dataclass(frozen=True)
class TemplateInstantiationResult:
    product_id: int
    landing_id: int
    slug: str


class LandingTemplateInstantiationService:
    def __init__(self, db: Prisma, r2: R2Client, *, public_host: str) -> None:
        self._db = db
        self._r2 = r2
        self._public_host = public_host

    async def creation_contract(self, template_id: int) -> dict[str, Any]:
        template = await self._db.landingtemplate.find_unique(where={"id": template_id})
        if template is None:
            raise TemplateNotFoundError(template_id)
        config = parse_template_config(template.config, banner_count=template.bannerCount)
        blocks = parse_template_blocks(template.blocks)
        requirements = describe_media_requirements(blocks, offer_count=config["offer_count"])
        return {
            "template_id": template.id,
            "template_name": template.name,
            "template_version": template.updatedAt.isoformat(),
            "banner_count": template.bannerCount,
            "media_blocks": [self._serialize_requirement(item) for item in requirements],
        }

    async def instantiate(
        self,
        template_id: int,
        *,
        template_version: str,
        product: dict[str, Any],
        slug: str,
        banners: list[dict[str, Any]],
        block_assets: list[dict[str, Any]],
        actor: str,
    ) -> TemplateInstantiationResult:
        template = await self._db.landingtemplate.find_unique(where={"id": template_id})
        if template is None:
            raise TemplateNotFoundError(template_id)
        if template_version != template.updatedAt.isoformat():
            raise TemplateVersionConflictError()

        if template.bannerCount < 1:
            raise LandingValidationError(
                "banner_count", "Una plantilla publicable debe requerir al menos un banner."
            )
        if len(banners) != template.bannerCount:
            raise LandingValidationError(
                "banners",
                f"La plantilla requiere exactamente {template.bannerCount} banners.",
            )

        validated_product = self._validate_product(product)
        validated_slug = self._validate_slug(slug)
        config = parse_template_config(template.config, banner_count=template.bannerCount)
        blocks = parse_template_blocks(template.blocks)
        requirements = describe_media_requirements(blocks, offer_count=config["offer_count"])
        assignments = validate_block_asset_assignments(requirements, block_assets)

        # Validate URL ownership and alt/caption bounds before reading or
        # writing any object. The source keys are deliberately retained only
        # in memory and are never persisted as the new assets' object keys.
        banner_inputs = [
            {
                "source_key": r2_original_object_key(
                    item.get("original_url", ""), public_host=self._public_host
                ),
                "original_url": item.get("original_url", ""),
                "alt_text": validate_alt_text(item.get("alt_text", "")),
            }
            for item in banners
        ]
        normalized_assignments = self._normalize_block_sources(assignments)

        existing_sku = await self._db.product.find_unique(where={"sku": validated_product["sku"]})
        if existing_sku is not None:
            raise DuplicateSkuError(validated_product["sku"])
        existing_slug = await self._db.landing.find_unique(where={"slug": validated_slug})
        if existing_slug is not None:
            raise DuplicateSlugError(validated_slug)

        uploaded_keys: list[str] = []
        try:
            prepared_banners = [
                await self._prepare_banner(item, uploaded_keys) for item in banner_inputs
            ]
            prepared_by_block = await self._prepare_block_media(
                requirements, normalized_assignments, uploaded_keys
            )
            return await self._persist(
                product=validated_product,
                slug=validated_slug,
                config=config,
                blocks=blocks,
                banners=prepared_banners,
                media=prepared_by_block,
                actor=actor,
            )
        except Exception:
            await self._cleanup(uploaded_keys)
            raise

    @staticmethod
    def _serialize_requirement(requirement: TemplateMediaRequirement) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "block_index": requirement.block_index,
            "block_type": requirement.block_type,
        }
        if requirement.maximum_videos is not None:
            payload["videos"] = {
                "minimum": requirement.minimum_videos,
                "maximum": requirement.maximum_videos,
            }
        if requirement.offer_quantities:
            payload["offer_images"] = {
                "required": True,
                "quantities": list(requirement.offer_quantities),
            }
        return payload

    @staticmethod
    def _validate_product(product: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": validate_name(str(product.get("name", ""))),
            "sku": validate_sku(str(product.get("sku", ""))),
            "price": validate_price(str(product.get("price", ""))),
            "description": validate_description(str(product.get("description", ""))),
            "variant_options": validate_variant_options(product.get("variant_options")),
        }

    @staticmethod
    def _validate_slug(slug: str) -> str:
        # Local import keeps this module's dependency list grouped by pipeline.
        from app.domains.landings.slug import validate_slug_format

        return cast(str, validate_slug_format(slug))

    def _normalize_block_sources(
        self, assignments: dict[int, dict[str, Any]]
    ) -> dict[int, dict[str, Any]]:
        normalized: dict[int, dict[str, Any]] = {}
        for block_index, assignment in assignments.items():
            videos: list[dict[str, Any]] = []
            for item in assignment.get("videos") or []:
                caption = str(item.get("caption") or "").strip()
                if len(caption) > 100:
                    raise LandingValidationError(
                        "caption", "El texto no puede superar 100 caracteres."
                    )
                url = item.get("original_url", "")
                videos.append(
                    {
                        "source_key": r2_original_object_key(
                            url, public_host=self._public_host
                        ),
                        "original_url": url,
                        "caption": caption or None,
                    }
                )
            offer_images: list[dict[str, Any]] = []
            for item in assignment.get("offer_images") or []:
                url = item.get("original_url", "")
                offer_images.append(
                    {
                        "source_key": r2_original_object_key(
                            url, public_host=self._public_host
                        ),
                        "original_url": url,
                        "quantity": item["quantity"],
                    }
                )
            normalized[block_index] = {"videos": videos, "offer_images": offer_images}
        return normalized

    async def _source_bytes(self, source: dict[str, Any]) -> bytes:
        try:
            return cast(bytes, await self._r2.get_bytes(source["source_key"]))
        except KeyError as exc:
            raise R2OriginalNotFoundError(source["original_url"]) from exc
        except Exception as exc:
            response = getattr(exc, "response", {})
            error = response.get("Error", {}) if isinstance(response, dict) else {}
            if str(error.get("Code", "")) in {"404", "NoSuchKey", "NotFound"}:
                raise R2OriginalNotFoundError(source["original_url"]) from exc
            raise ImagePipelineUnavailableError() from exc

    async def _prepare_banner(
        self, source: dict[str, Any], uploaded_keys: list[str]
    ) -> PreparedBanner:
        raw_bytes = await self._source_bytes(source)
        validated = validate_source_image(raw_bytes)
        clean = strip_exif(validated.image)
        variants = generate_variants(clean)
        edges = extract_edge_colors(clean)
        opaque_key = generate_opaque_key()
        extension = _SOURCE_EXTENSION_BY_FORMAT[validated.format]
        source_key = original_object_key(opaque_key, extension)
        await self._put(source_key, raw_bytes, _CONTENT_TYPE_BY_EXTENSION[extension], uploaded_keys)
        keyed_variants: list[PreparedImageVariant] = []
        for variant in variants:
            key = variant_object_key(opaque_key, variant.width, variant.format)
            await self._put(
                key, variant.data, _CONTENT_TYPE_BY_EXTENSION[variant.format], uploaded_keys
            )
            keyed_variants.append(
                PreparedImageVariant(
                    width=variant.width,
                    height=variant.height,
                    format=variant.format,
                    object_key=key,
                )
            )
        return PreparedBanner(
            alt_text=source["alt_text"],
            opaque_key=opaque_key,
            source_key=source_key,
            source_width=validated.width,
            source_height=validated.height,
            source_format=validated.format.lower(),
            variants=tuple(keyed_variants),
            edges=edges,
        )

    async def _prepare_block_media(
        self,
        requirements: list[TemplateMediaRequirement],
        assignments: dict[int, dict[str, Any]],
        uploaded_keys: list[str],
    ) -> dict[int, PreparedBlockMedia]:
        result: dict[int, PreparedBlockMedia] = {}
        for requirement in requirements:
            assignment = assignments.get(requirement.block_index, {})
            videos = [
                await self._prepare_video(item, uploaded_keys)
                for item in assignment.get("videos", [])
            ]
            offer_images = [
                await self._prepare_offer_image(item, uploaded_keys)
                for item in assignment.get("offer_images", [])
            ]
            result[requirement.block_index] = PreparedBlockMedia(
                videos=tuple(videos), offer_images=tuple(offer_images)
            )
        return result

    async def _prepare_offer_image(
        self, source: dict[str, Any], uploaded_keys: list[str]
    ) -> PreparedOfferImage:
        raw_bytes = await self._source_bytes(source)
        validated = validate_source_image(raw_bytes)
        clean = strip_exif(ImageOps.exif_transpose(validated.image))
        optimized = await asyncio.to_thread(optimize_offer_image, clean)
        opaque_key = generate_opaque_key()
        extension = _SOURCE_EXTENSION_BY_FORMAT[validated.format]
        source_key = original_object_key(opaque_key, extension)
        image_key = offer_image_object_key(opaque_key)
        await self._put(source_key, raw_bytes, _CONTENT_TYPE_BY_EXTENSION[extension], uploaded_keys)
        await self._put(image_key, optimized.data, "image/webp", uploaded_keys)
        return PreparedOfferImage(
            quantity=source["quantity"],
            opaque_key=opaque_key,
            source_key=source_key,
            image_key=image_key,
            optimized=optimized,
        )

    async def _prepare_video(
        self, source: dict[str, Any], uploaded_keys: list[str]
    ) -> PreparedVideo:
        raw_bytes = await self._source_bytes(source)
        optimized = await asyncio.to_thread(optimize_video, raw_bytes)
        opaque_key = generate_opaque_key()
        video_key = video_object_key(opaque_key)
        poster_key = video_poster_object_key(opaque_key)
        await self._put(video_key, optimized.video, "video/mp4", uploaded_keys)
        await self._put(poster_key, optimized.poster, "image/webp", uploaded_keys)
        return PreparedVideo(
            caption=source["caption"],
            opaque_key=opaque_key,
            video_key=video_key,
            poster_key=poster_key,
            optimized=optimized,
        )

    async def _put(
        self, key: str, data: bytes, content_type: str, uploaded_keys: list[str]
    ) -> None:
        try:
            await self._r2.put_bytes(key, data, content_type=content_type)
        except Exception as exc:
            raise ImagePipelineUnavailableError() from exc
        uploaded_keys.append(key)

    async def _persist(
        self,
        *,
        product: dict[str, Any],
        slug: str,
        config: dict[str, Any],
        blocks: list[dict[str, Any]],
        banners: list[PreparedBanner],
        media: dict[int, PreparedBlockMedia],
        actor: str,
    ) -> TemplateInstantiationResult:
        async with self._db.tx() as tx:
            if await tx.product.find_unique(where={"sku": product["sku"]}) is not None:
                raise DuplicateSkuError(product["sku"])
            if await tx.landing.find_unique(where={"slug": slug}) is not None:
                raise DuplicateSlugError(slug)

            stored_product = await tx.product.create(
                data={
                    "name": product["name"],
                    "sku": product["sku"],
                    "price": product["price"],
                    "description": product["description"],
                    "variantOptions": Json(product["variant_options"]),
                    "status": "active",
                }
            )
            landing = await tx.landing.create(
                data={
                    "productId": stored_product.id,
                    "slug": slug,
                    "status": "draft",
                    "ctaMode": config["cta_mode"],
                    "ctaInterval": config["cta_interval"],
                    "ctaPositions": config["cta_positions"],
                    "ctaBandStyle": config["cta_band_style"],
                    "ctaText": config["cta_text"],
                    "ctaAnimation": config["cta_animation"],
                    "ctaTextOverrides": Json(config["cta_text_overrides"]),
                    "ctaColorModes": Json(config["cta_color_modes"]),
                    "formPresentation": config["form_presentation"],
                    "accentColor": config["accent_color"],
                    "formAccentColor": config["form_accent_color"],
                    "blocksAccentColor": config["blocks_accent_color"],
                    "blocksDarkMode": config["blocks_dark_mode"],
                    "offerCount": config["offer_count"],
                    "defaultOfferQuantity": config["default_offer_quantity"],
                    "offers": Json(config["offers"]),
                }
            )

            for order_index, prepared in enumerate(banners):
                asset = await tx.imageasset.create(
                    data={
                        "opaqueKey": prepared.opaque_key,
                        "sourceObjectKey": prepared.source_key,
                        "sourceWidth": prepared.source_width,
                        "sourceHeight": prepared.source_height,
                        "sourceFormat": prepared.source_format,
                        "status": "complete",
                        "topEdgeColor": prepared.edges.top.color,
                        "bottomEdgeColor": prepared.edges.bottom.color,
                        "topEdgeFlat": prepared.edges.top.flat,
                        "bottomEdgeFlat": prepared.edges.bottom.flat,
                    }
                )
                for variant in prepared.variants:
                    await tx.imagevariant.create(
                        data={
                            "imageAssetId": asset.id,
                            "width": variant.width,
                            "height": variant.height,
                            "format": variant.format,
                            "objectKey": variant.object_key,
                            "version": prepared.opaque_key,
                        }
                    )
                banner = await tx.banner.create(
                    data={
                        "landingId": landing.id,
                        "orderIndex": order_index,
                        "altText": prepared.alt_text,
                        "imageAssetId": asset.id,
                    }
                )
                await self._audit(tx, actor, "banner.upload", "banner", banner.id)

            for block_index, entry in enumerate(blocks):
                block = await tx.landingblock.create(
                    data={
                        "landingId": landing.id,
                        "blockType": entry["block_type"],
                        "slotIndex": entry["slot_index"],
                        "orderIndex": entry["order_index"],
                        "config": Json(entry["config"]),
                        "enabled": entry["enabled"],
                    }
                )
                block_media = media.get(block_index, PreparedBlockMedia())
                for order_index, prepared in enumerate(block_media.videos):
                    video = await tx.videoasset.create(
                        data={
                            "landingBlockId": block.id,
                            "opaqueKey": prepared.opaque_key,
                            "videoObjectKey": prepared.video_key,
                            "posterObjectKey": prepared.poster_key,
                            "width": prepared.optimized.width,
                            "height": prepared.optimized.height,
                            "durationMs": prepared.optimized.duration_ms,
                            "byteSize": len(prepared.optimized.video),
                            "orderIndex": order_index,
                            "caption": prepared.caption,
                        }
                    )
                    await self._audit(tx, actor, "video.upload", "video_asset", video.id)
                for prepared in block_media.offer_images:
                    image = await tx.offerimageasset.create(
                        data={
                            "landingBlockId": block.id,
                            "quantity": prepared.quantity,
                            "opaqueKey": prepared.opaque_key,
                            "sourceObjectKey": prepared.source_key,
                            "imageObjectKey": prepared.image_key,
                            "width": prepared.optimized.width,
                            "height": prepared.optimized.height,
                            "byteSize": len(prepared.optimized.data),
                        }
                    )
                    await self._audit(
                        tx, actor, "offer_image.upload", "offer_image_asset", image.id
                    )

            await tx.landing.update(where={"id": landing.id}, data={"status": "published"})
            await self._audit(tx, actor, "product.create", "product", stored_product.id)
            await self._audit(tx, actor, "landing_template.instantiate", "landing", landing.id)
            await self._audit(tx, actor, "landing.publish", "landing", landing.id)

        return TemplateInstantiationResult(
            product_id=stored_product.id,
            landing_id=landing.id,
            slug=slug,
        )

    @staticmethod
    async def _audit(
        tx: Any, actor: str, action: str, target_type: str, target_id: int
    ) -> None:
        await tx.auditlog.create(
            data={
                "actor": actor,
                "action": action,
                "targetType": target_type,
                "targetId": str(target_id),
                "result": "success",
            }
        )

    async def _cleanup(self, keys: list[str]) -> None:
        for key in reversed(keys):
            with contextlib.suppress(Exception):
                await self._r2.delete(key)


__all__ = [
    "LandingTemplateInstantiationService",
    "R2OriginalNotFoundError",
    "TemplateInstantiationResult",
    "TemplateVersionConflictError",
    "VideoPipelineError",
]
