"""Admin Landings API router: landing config, banner upload/order, publication.

Thin HTTP layer over `LandingManagementService`, `BannerUploadService`, and
`LandingPublicationService` (design.md -> API Design -> Landings & Banners).

Error mapping, applied uniformly to every endpoint here:

- `LandingNotFoundError` / `BannerNotFoundError` -> `404`
- `LandingValidationError` / `ImageValidationError` -> `422` with
  `{"field", "message"}` so the dashboard can bind the message to the
  control that produced it (Requirement 8.19)
- `PublicationValidationError` -> `422` (Requirement 3.20)
- `DuplicateSlugError` / `BannerLimitExceededError` -> `409`
  (Requirements 3.2, 3.6)
- `ImagePipelineUnavailableError` / `OpaqueKeyGenerationError` -> `503` with
  a non-sensitive message (Requirements 4.21, 10.20)
"""

from __future__ import annotations

import contextlib

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.core.auth_dependencies import require_admin
from app.core.settings import Settings, get_settings
from app.db.client import get_prisma
from app.domains.images.errors import (
    ImagePipelineUnavailableError,
    ImageValidationError,
    OpaqueKeyGenerationError,
)
from app.domains.images.validation import SOURCE_MAX_BYTES
from app.domains.landings.accent_color import DEFAULT_ACCENT_COLOR
from app.domains.landings.blocks import ALLOWED_BLOCK_TYPES
from app.domains.landings.cta_placement import compute_cta_positions, validate_cta_config
from app.domains.landings.errors import (
    BannerLimitExceededError,
    BannerNotFoundError,
    DuplicateSlugError,
    LandingNotFoundError,
    LandingValidationError,
    PublicationValidationError,
)
from app.domains.landings.offers import parse_stored_offers, resolve_offer_pricing
from app.domains.videos import SOURCE_VIDEO_MAX_BYTES, VideoPipelineError, VideoValidationError
from app.services.banner_upload_service import BannerUploadService
from app.services.landing_block_service import BlockNotFoundError, LandingBlockService
from app.services.landing_management_service import LandingManagementService
from app.services.landing_publication_service import LandingPublicationService
from app.services.landing_template_service import (
    LandingTemplateService,
    TemplateNotFoundError,
)
from app.services.video_upload_service import VideoNotFoundError, VideoUploadService
from app.storage.dependencies import get_r2_client
from app.storage.r2_client import R2Client, object_public_url, variant_public_url

router = APIRouter(prefix="/api/admin/landings", tags=["admin", "landings"])

_UPLOAD_UNAVAILABLE_MESSAGE = "Image upload is temporarily unavailable. Please try again."
_VIDEO_CONTENT_TYPES = {"video/mp4", "video/webm", "video/quicktime", "video/x-m4v"}


class ImageVariantResponse(BaseModel):
    width: int
    height: int
    format: str
    url: str


class BannerResponse(BaseModel):
    id: int
    alt_text: str
    order_index: int
    image_asset_id: int
    image_status: str
    variants: list[ImageVariantResponse]
    # Precomputed at upload, exposed so the dashboard preview paints the same
    # CTA bands as the public landing (None only when no color was extracted).
    top_edge_color: str | None = None
    bottom_edge_color: str | None = None


class LandingOfferResponse(BaseModel):
    """One configured quantity offer.

    `sublabel` is `None` when the merchant left the sub-text blank, which is how
    a tile renders without a second line. `discount_percent` is only ever
    non-zero for multi-unit offers; `discount_amount` is its mutually exclusive
    COP alternative. `compare_at_price` only applies to the single-unit offer.
    """

    quantity: int
    label: str
    sublabel: str | None = None
    discount_percent: int = 0
    discount_amount: float | None = None
    calculated_discount_percent: int = 0
    compare_at_price: float | None = None


class LandingSummaryResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    product_sku: str
    product_status: str
    slug: str
    status: str
    cta_mode: str
    cta_interval: int | None
    cta_positions: list[int]
    form_presentation: str
    cta_band_style: str
    accent_color: str
    form_accent_color: str | None = None
    blocks_accent_color: str | None = None
    offer_count: int
    default_offer_quantity: int
    offers: list[LandingOfferResponse]
    banner_count: int
    cta_text: str | None = None
    cta_animation: str | None = None
    # Per-CTA-position text override: `{"2": "Lo quiero ahora"}` overrides
    # only the second CTA's label, leaving the rest on `cta_text`/default.
    cta_text_overrides: dict[str, str] = {}
    # Per-position CTA band mode. Missing positions use the sampled banner
    # background; stored values are "dark" or "light".
    cta_color_modes: dict[str, str] = {}
    blocks_dark_mode: bool = False


class LandingListResponse(BaseModel):
    landings: list[LandingSummaryResponse]


class LandingDetailResponse(LandingSummaryResponse):
    banners: list[BannerResponse]
    resolved_cta_positions: list[int]


class BannerListResponse(BaseModel):
    banners: list[BannerResponse]


class LandingOfferUpdate(BaseModel):
    """One offer as submitted by the dashboard.

    Blank `sublabel` is meaningful (no sub-text), so it is accepted as an empty
    string rather than requiring the client to omit the key.
    """

    quantity: int
    label: str
    sublabel: str | None = None
    discount_percent: int | None = None
    discount_amount: float | None = None
    compare_at_price: float | None = None


class LandingConfigUpdateRequest(BaseModel):
    slug: str | None = None
    cta_mode: str | None = None
    cta_interval: int | None = None
    cta_positions: list[int] | None = None
    form_presentation: str | None = None
    cta_band_style: str | None = None
    accent_color: str | None = None
    form_accent_color: str | None = None
    blocks_accent_color: str | None = None
    offer_count: int | None = None
    default_offer_quantity: int | None = None
    offers: list[LandingOfferUpdate] | None = None
    cta_text: str | None = None
    cta_animation: str | None = None
    cta_text_overrides: dict[str, str] | None = None
    cta_color_modes: dict[str, str] | None = None
    blocks_dark_mode: bool | None = None


class BannerUpdateRequest(BaseModel):
    alt_text: str | None = None
    order_index: int | None = None


class BannerOrderRequest(BaseModel):
    banner_ids: list[int]


class LandingBlockResponse(BaseModel):
    """One placed conversion component.

    `slot_index` counts the rendered elements the component follows (0 = above
    everything), and `config` carries content only — presentation for each type
    is fixed in the Landing chrome.
    """

    id: int
    block_type: str
    slot_index: int
    order_index: int
    enabled: bool
    config: dict
    videos: list[VideoAssetResponse] = []


class VideoAssetResponse(BaseModel):
    id: int
    url: str
    poster_url: str
    width: int
    height: int
    duration_ms: int
    byte_size: int
    order_index: int
    caption: str | None = None


class LandingBlockListResponse(BaseModel):
    blocks: list[LandingBlockResponse]
    """Labels for every placement slot, index 0 first."""
    slots: list[str]
    allowed_block_types: list[str]


class LandingBlockCreateRequest(BaseModel):
    block_type: str
    slot_index: int
    config: dict = {}
    enabled: bool = True


class LandingBlockUpdateRequest(BaseModel):
    slot_index: int | None = None
    config: dict | None = None
    enabled: bool | None = None


class LandingLoadTemplateRequest(BaseModel):
    """Which saved template to apply to this landing."""

    template_id: int


def _field_error(field: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"field": field, "message": message},
    )


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


def _to_banner_response(banner, public_host: str) -> BannerResponse:  # type: ignore[no-untyped-def]
    """Map a Banner row to its admin payload.

    `imageAsset` (with `variants`) is included by the caller's query when the
    payload needs preview candidates; when the relation is absent the banner
    is still returned with an empty candidate list so the dashboard can show
    and manage the row instead of failing the whole request.
    """
    image_asset = getattr(banner, "imageAsset", None)
    variants: list[ImageVariantResponse] = []
    if image_asset is not None:
        for variant in sorted(
            image_asset.variants or [], key=lambda item: (item.width, item.format)
        ):
            variants.append(
                ImageVariantResponse(
                    width=variant.width,
                    height=variant.height,
                    format=variant.format,
                    url=variant_public_url(
                        public_host, image_asset.opaqueKey, variant.width, variant.format
                    ),
                )
            )
    return BannerResponse(
        id=banner.id,
        alt_text=banner.altText,
        order_index=banner.orderIndex,
        image_asset_id=banner.imageAssetId,
        image_status=image_asset.status if image_asset is not None else "unknown",
        variants=variants,
        # `*_edge_flat` is not consulted here for the same reason the public
        # router ignores it: the strip mean is the least-wrong single color for
        # that edge, and the preview has to match what visitors see.
        top_edge_color=image_asset.topEdgeColor if image_asset is not None else None,
        bottom_edge_color=image_asset.bottomEdgeColor if image_asset is not None else None,
    )


def _to_summary_response(landing) -> LandingSummaryResponse:  # type: ignore[no-untyped-def]
    product = landing.product
    banners = landing.banners or []
    # Read leniently: a stored tier list that drifted from `offer_count` still
    # has to open in the dashboard so the merchant can repair it.
    offers = parse_stored_offers(landing.offers, offer_count=landing.offerCount)
    return LandingSummaryResponse(
        id=landing.id,
        product_id=landing.productId,
        product_name=product.name if product else "",
        product_sku=product.sku if product else "",
        product_status=product.status if product else "unknown",
        slug=landing.slug,
        status=landing.status,
        cta_mode=landing.ctaMode,
        cta_interval=landing.ctaInterval,
        cta_positions=list(landing.ctaPositions or []),
        form_presentation=landing.formPresentation,
        cta_band_style=landing.ctaBandStyle,
        accent_color=landing.accentColor or DEFAULT_ACCENT_COLOR,
        form_accent_color=landing.formAccentColor,
        blocks_accent_color=getattr(landing, "blocksAccentColor", None),
        offer_count=landing.offerCount,
        default_offer_quantity=getattr(landing, "defaultOfferQuantity", 1),
        offers=[
            LandingOfferResponse(
                quantity=offer.quantity,
                label=offer.label,
                sublabel=offer.sublabel,
                discount_percent=offer.discount_percent,
                discount_amount=(
                    None if offer.discount_amount is None else float(offer.discount_amount)
                ),
                calculated_discount_percent=resolve_offer_pricing(
                    product.price, offer
                ).discount_percent,
                compare_at_price=(
                    None if offer.compare_at_price is None else float(offer.compare_at_price)
                ),
            )
            for offer in offers
        ],
        banner_count=len(banners),
        cta_text=landing.ctaText,
        cta_animation=landing.ctaAnimation,
        cta_text_overrides=(
            landing.ctaTextOverrides if isinstance(landing.ctaTextOverrides, dict) else {}
        ),
        cta_color_modes=(
            landing.ctaColorModes
            if isinstance(getattr(landing, "ctaColorModes", None), dict)
            else {}
        ),
        blocks_dark_mode=bool(landing.blocksDarkMode),
    )


def _to_detail_response(landing, public_host: str) -> LandingDetailResponse:  # type: ignore[no-untyped-def]
    summary = _to_summary_response(landing)
    stored_banners = sorted(landing.banners or [], key=lambda item: item.orderIndex)
    banners = [_to_banner_response(banner, public_host) for banner in stored_banners]

    # A stored configuration can be temporarily inconsistent with the current
    # banner count (e.g. fixed positions kept while banners are removed).
    # The dashboard still needs to open the landing to repair it, so an
    # invalid configuration yields no resolved positions rather than an error;
    # publication is where it is enforced (Requirement 3.20).
    try:
        config = validate_cta_config(
            summary.cta_mode,
            interval=summary.cta_interval,
            positions=summary.cta_positions or None,
        )
        resolved = compute_cta_positions(config, len(banners))
    except LandingValidationError:
        resolved = []

    return LandingDetailResponse(
        **summary.model_dump(),
        banners=banners,
        resolved_cta_positions=resolved,
    )


_LANDING_DETAIL_INCLUDE = {
    "product": True,
    "banners": {"include": {"imageAsset": {"include": {"variants": True}}}},
}


@router.get("", response_model=LandingListResponse)
async def list_landings(
    include_retired: bool = False,
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> LandingListResponse:
    """List landings with their product and banner counts.

    Landings of retired products are excluded by default, matching the
    product list's `include_retired` behavior.
    """
    db = get_prisma()

    where = None if include_retired else {"product": {"is": {"status": {"not": "retired"}}}}
    landings = await db.landing.find_many(
        where=where,  # type: ignore[arg-type]
        include={"product": True, "banners": True},
        order={"id": "asc"},
    )
    return LandingListResponse(landings=[_to_summary_response(landing) for landing in landings])


@router.get("/{landing_id}", response_model=LandingDetailResponse)
async def get_landing(
    landing_id: int,
    settings: Settings = Depends(get_settings),  # noqa: B008 (FastAPI DI convention)
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> LandingDetailResponse:
    """Return one landing's configuration and full banner sequence."""
    db = get_prisma()

    landing = await db.landing.find_unique(
        where={"id": landing_id},
        include=_LANDING_DETAIL_INCLUDE,  # type: ignore[arg-type]
    )
    if landing is None:
        raise _not_found("Landing not found")

    return _to_detail_response(landing, settings.r2_public_host)


@router.patch("/{landing_id}", response_model=LandingDetailResponse)
async def update_landing_config(
    landing_id: int,
    request: LandingConfigUpdateRequest,
    settings: Settings = Depends(get_settings),  # noqa: B008 (FastAPI DI convention)
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> LandingDetailResponse:
    """Update slug, CTA configuration/band style, COD form presentation,
    accent color, and the quantity offers the form presents."""
    db = get_prisma()
    service = LandingManagementService(db)

    # PATCH distinguishes an omitted field (leave unchanged) from an explicit
    # null (clear the override). The service represents an explicit clear with
    # an empty string.
    form_accent_color = request.form_accent_color
    if "form_accent_color" in request.model_fields_set and form_accent_color is None:
        form_accent_color = ""
    blocks_accent_color = request.blocks_accent_color
    if "blocks_accent_color" in request.model_fields_set and blocks_accent_color is None:
        blocks_accent_color = ""

    try:
        await service.update_config(
            landing_id,
            slug=request.slug,
            cta_mode=request.cta_mode,
            cta_interval=request.cta_interval,
            cta_positions=request.cta_positions,
            form_presentation=request.form_presentation,
            cta_band_style=request.cta_band_style,
            accent_color=request.accent_color,
            form_accent_color=form_accent_color,
            blocks_accent_color=blocks_accent_color,
            offer_count=request.offer_count,
            default_offer_quantity=request.default_offer_quantity,
            offers=(
                None if request.offers is None else [offer.model_dump() for offer in request.offers]
            ),
            cta_text=request.cta_text,
            cta_animation=request.cta_animation,
            cta_text_overrides=request.cta_text_overrides,
            cta_color_modes=request.cta_color_modes,
            blocks_dark_mode=request.blocks_dark_mode,
            actor=admin_user.subject,
        )
    except LandingNotFoundError as exc:
        raise _not_found("Landing not found") from exc
    except DuplicateSlugError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except LandingValidationError as exc:
        raise _field_error(exc.field, exc.message) from exc

    return await get_landing(landing_id, settings=settings, admin_user=admin_user)


@router.post(
    "/{landing_id}/banners",
    response_model=BannerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_banner(
    landing_id: int,
    file: UploadFile = File(...),  # noqa: B008 (FastAPI multipart convention)
    alt_text: str = Form(...),  # noqa: B008 (FastAPI multipart convention)
    settings: Settings = Depends(get_settings),  # noqa: B008 (FastAPI DI convention)
    r2: R2Client = Depends(get_r2_client),  # noqa: B008 (FastAPI DI convention)
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> BannerResponse:
    """Upload a banner image and append it to the landing's sequence.

    Runs the full image pipeline (decode/validate -> EXIF strip -> variants
    -> R2 -> atomic persistence). The upload is rejected before any database
    row or R2 object survives when validation fails or R2 is unreachable.
    """
    db = get_prisma()

    # Read one byte past the documented limit so an oversized upload is
    # rejected as a field error without buffering the whole body.
    raw_bytes = await file.read(SOURCE_MAX_BYTES + 1)
    if len(raw_bytes) > SOURCE_MAX_BYTES:
        raise _field_error(
            "file", f"File exceeds the maximum size of {SOURCE_MAX_BYTES} bytes (10 MiB)."
        )

    service = BannerUploadService(db, r2)
    try:
        result = await service.upload_banner(
            landing_id,
            raw_bytes=raw_bytes,
            alt_text=alt_text,
            actor=admin_user.subject,
        )
    except LandingNotFoundError as exc:
        raise _not_found("Landing not found") from exc
    except BannerLimitExceededError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ImageValidationError as exc:
        raise _field_error(exc.field, exc.message) from exc
    except LandingValidationError as exc:
        raise _field_error(exc.field, exc.message) from exc
    except (ImagePipelineUnavailableError, OpaqueKeyGenerationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_UPLOAD_UNAVAILABLE_MESSAGE,
        ) from exc

    stored = await db.banner.find_unique(
        where={"id": result.banner.id},
        include={"imageAsset": {"include": {"variants": True}}},
    )
    return _to_banner_response(stored or result.banner, settings.r2_public_host)


@router.patch("/{landing_id}/banners/{banner_id}", response_model=BannerListResponse)
async def update_banner(
    landing_id: int,
    banner_id: int,
    request: BannerUpdateRequest,
    settings: Settings = Depends(get_settings),  # noqa: B008 (FastAPI DI convention)
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> BannerListResponse:
    """Update a banner's alternative text and/or its position in the sequence."""
    db = get_prisma()
    service = LandingManagementService(db)

    try:
        await service.update_banner(
            landing_id,
            banner_id,
            alt_text=request.alt_text,
            order_index=request.order_index,
            actor=admin_user.subject,
        )
    except LandingNotFoundError as exc:
        raise _not_found("Landing not found") from exc
    except BannerNotFoundError as exc:
        raise _not_found("Banner not found") from exc
    except LandingValidationError as exc:
        raise _field_error(exc.field, exc.message) from exc

    return await _banner_list(landing_id, settings.r2_public_host)


@router.put("/{landing_id}/banners/order", response_model=BannerListResponse)
async def reorder_banners(
    landing_id: int,
    request: BannerOrderRequest,
    settings: Settings = Depends(get_settings),  # noqa: B008 (FastAPI DI convention)
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> BannerListResponse:
    """Apply an explicit full ordering of the landing's banners."""
    db = get_prisma()
    service = LandingManagementService(db)

    try:
        await service.reorder_banners(landing_id, request.banner_ids, actor=admin_user.subject)
    except LandingNotFoundError as exc:
        raise _not_found("Landing not found") from exc
    except LandingValidationError as exc:
        raise _field_error(exc.field, exc.message) from exc

    return await _banner_list(landing_id, settings.r2_public_host)


@router.delete("/{landing_id}/banners/{banner_id}", response_model=BannerListResponse)
async def delete_banner(
    landing_id: int,
    banner_id: int,
    settings: Settings = Depends(get_settings),  # noqa: B008 (FastAPI DI convention)
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> BannerListResponse:
    """Remove a banner and close the position gap it leaves behind."""
    db = get_prisma()
    service = LandingManagementService(db)

    try:
        await service.delete_banner(landing_id, banner_id, actor=admin_user.subject)
    except LandingNotFoundError as exc:
        raise _not_found("Landing not found") from exc
    except BannerNotFoundError as exc:
        raise _not_found("Banner not found") from exc

    return await _banner_list(landing_id, settings.r2_public_host)


@router.post("/{landing_id}/publish", response_model=LandingDetailResponse)
async def publish_landing(
    landing_id: int,
    settings: Settings = Depends(get_settings),  # noqa: B008 (FastAPI DI convention)
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> LandingDetailResponse:
    """Publish a landing with 1-15 banners and a valid CTA configuration."""
    db = get_prisma()
    service = LandingPublicationService(db)

    try:
        await service.publish(landing_id, actor=admin_user.subject)
    except LandingNotFoundError as exc:
        raise _not_found("Landing not found") from exc
    except PublicationValidationError as exc:
        raise _field_error("banners", exc.message) from exc

    return await get_landing(landing_id, settings=settings, admin_user=admin_user)


@router.post("/{landing_id}/unpublish", response_model=LandingDetailResponse)
async def unpublish_landing(
    landing_id: int,
    settings: Settings = Depends(get_settings),  # noqa: B008 (FastAPI DI convention)
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> LandingDetailResponse:
    """Return a published landing to draft, making it publicly unavailable."""
    db = get_prisma()
    service = LandingPublicationService(db)

    try:
        await service.unpublish(landing_id, actor=admin_user.subject)
    except LandingNotFoundError as exc:
        raise _not_found("Landing not found") from exc

    return await get_landing(landing_id, settings=settings, admin_user=admin_user)


@router.post("/{landing_id}/load-template", response_model=LandingDetailResponse)
async def load_landing_template(
    landing_id: int,
    request: LandingLoadTemplateRequest,
    settings: Settings = Depends(get_settings),  # noqa: B008 (FastAPI DI convention)
    r2: R2Client = Depends(get_r2_client),  # noqa: B008
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> LandingDetailResponse:
    """Apply a saved template's configuration and components to this landing.

    Refused with a 422 on `banner_count` unless the landing has exactly the
    template's number of banners: the template's CTA positions and component
    slots address places in the rendered sequence, so applying it to a sequence
    of a different length would move or drop components silently.

    Banners, slug, product, and publication status are never touched.
    """
    db = get_prisma()
    service = LandingTemplateService(db)
    current_blocks = await db.landingblock.find_many(
        where={"landingId": landing_id}, include={"videos": True}
    )
    replaced_video_keys = [
        key
        for block in current_blocks
        for video in (getattr(block, "videos", None) or [])
        for key in (video.videoObjectKey, video.posterObjectKey)
    ]
    try:
        await service.load_template(landing_id, request.template_id, actor=admin_user.subject)
    except LandingNotFoundError as exc:
        raise _not_found("Landing not found") from exc
    except TemplateNotFoundError as exc:
        raise _not_found("Landing template not found") from exc
    except LandingValidationError as exc:
        raise _field_error(exc.field, exc.message) from exc

    for key in replaced_video_keys:
        with contextlib.suppress(Exception):
            await r2.delete(key)

    return await get_landing(landing_id, settings=settings, admin_user=admin_user)


async def _banner_list(landing_id: int, public_host: str) -> BannerListResponse:
    db = get_prisma()
    stored = await db.banner.find_many(
        where={"landingId": landing_id},
        include={"imageAsset": {"include": {"variants": True}}},
        order={"orderIndex": "asc"},
    )
    return BannerListResponse(
        banners=[_to_banner_response(banner, public_host) for banner in stored]
    )


# ---------------------------------------------------------------------------
# Conversion components (Requirements 3.27-3.31)
# ---------------------------------------------------------------------------


def _to_block_response(block, public_host: str) -> LandingBlockResponse:  # type: ignore[no-untyped-def]
    return LandingBlockResponse(
        id=block.id,
        block_type=block.blockType,
        slot_index=block.slotIndex,
        order_index=block.orderIndex,
        enabled=block.enabled,
        config=block.config if isinstance(block.config, dict) else {},
        videos=[
            VideoAssetResponse(
                id=video.id,
                url=object_public_url(public_host, video.videoObjectKey),
                poster_url=object_public_url(public_host, video.posterObjectKey),
                width=video.width,
                height=video.height,
                duration_ms=video.durationMs,
                byte_size=video.byteSize,
                order_index=video.orderIndex,
                caption=video.caption,
            )
            for video in sorted(
                getattr(block, "videos", None) or [], key=lambda item: item.orderIndex
            )
        ],
    )


async def _block_list(landing_id: int) -> LandingBlockListResponse:
    db = get_prisma()
    service = LandingBlockService(db)
    blocks = await db.landingblock.find_many(
        where={"landingId": landing_id},
        include={"videos": True},
        order=[{"slotIndex": "asc"}, {"orderIndex": "asc"}],
    )
    settings = get_settings()
    return LandingBlockListResponse(
        blocks=[_to_block_response(block, settings.r2_public_host) for block in blocks],
        slots=await service.describe_slots(landing_id),
        allowed_block_types=list(ALLOWED_BLOCK_TYPES),
    )


@router.post(
    "/{landing_id}/blocks/{block_id}/videos",
    response_model=LandingBlockListResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_block_video(
    landing_id: int,
    block_id: int,
    file: UploadFile = File(...),  # noqa: B008
    caption: str = Form(""),  # noqa: B008
    r2: R2Client = Depends(get_r2_client),  # noqa: B008
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008
) -> LandingBlockListResponse:
    if file.content_type not in _VIDEO_CONTENT_TYPES:
        raise _field_error("file", "Selecciona un archivo MP4, WebM o MOV válido.")
    raw_bytes = await file.read(SOURCE_VIDEO_MAX_BYTES + 1)
    try:
        await VideoUploadService(get_prisma(), r2).upload(
            landing_id, block_id, raw_bytes=raw_bytes, caption=caption, actor=admin_user.subject
        )
    except LandingNotFoundError as exc:
        raise _not_found("Landing or component not found") from exc
    except (LandingValidationError, VideoValidationError) as exc:
        raise _field_error(exc.field, exc.message) from exc
    except VideoPipelineError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return await _block_list(landing_id)


@router.delete(
    "/{landing_id}/blocks/{block_id}/videos/{video_id}",
    response_model=LandingBlockListResponse,
)
async def delete_block_video(
    landing_id: int,
    block_id: int,
    video_id: int,
    r2: R2Client = Depends(get_r2_client),  # noqa: B008
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008
) -> LandingBlockListResponse:
    try:
        await VideoUploadService(get_prisma(), r2).delete(
            landing_id, block_id, video_id, actor=admin_user.subject
        )
    except VideoNotFoundError as exc:
        raise _not_found("Video not found") from exc
    return await _block_list(landing_id)


@router.get("/{landing_id}/blocks", response_model=LandingBlockListResponse)
async def list_landing_blocks(
    landing_id: int,
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> LandingBlockListResponse:
    """List placed conversion components plus the landing's placement slots."""
    try:
        return await _block_list(landing_id)
    except LandingNotFoundError as exc:
        raise _not_found("Landing not found") from exc


@router.post(
    "/{landing_id}/blocks",
    response_model=LandingBlockListResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_landing_block(
    landing_id: int,
    request: LandingBlockCreateRequest,
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> LandingBlockListResponse:
    """Place a conversion component in a slot of the rendered sequence."""
    service = LandingBlockService(get_prisma())
    try:
        await service.create_block(
            landing_id,
            block_type=request.block_type,
            slot_index=request.slot_index,
            config=request.config,
            enabled=request.enabled,
            actor=admin_user.subject,
        )
    except LandingNotFoundError as exc:
        raise _not_found("Landing not found") from exc
    except LandingValidationError as exc:
        raise _field_error(exc.field, exc.message) from exc

    return await _block_list(landing_id)


@router.patch("/{landing_id}/blocks/{block_id}", response_model=LandingBlockListResponse)
async def update_landing_block(
    landing_id: int,
    block_id: int,
    request: LandingBlockUpdateRequest,
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> LandingBlockListResponse:
    """Update a component's content, position, and/or enabled state."""
    service = LandingBlockService(get_prisma())
    try:
        await service.update_block(
            landing_id,
            block_id,
            slot_index=request.slot_index,
            config=request.config,
            enabled=request.enabled,
            actor=admin_user.subject,
        )
    except LandingNotFoundError as exc:
        raise _not_found("Landing not found") from exc
    except BlockNotFoundError as exc:
        raise _not_found("Conversion component not found") from exc
    except LandingValidationError as exc:
        raise _field_error(exc.field, exc.message) from exc

    return await _block_list(landing_id)


@router.delete("/{landing_id}/blocks/{block_id}", response_model=LandingBlockListResponse)
async def delete_landing_block(
    landing_id: int,
    block_id: int,
    r2: R2Client = Depends(get_r2_client),  # noqa: B008
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> LandingBlockListResponse:
    """Remove a placed conversion component."""
    db = get_prisma()
    service = LandingBlockService(db)
    stored = await db.landingblock.find_first(
        where={"id": block_id, "landingId": landing_id}, include={"videos": True}
    )
    removed_video_keys = [
        key
        for video in (getattr(stored, "videos", None) or [])
        for key in (video.videoObjectKey, video.posterObjectKey)
    ]
    try:
        await service.delete_block(landing_id, block_id, actor=admin_user.subject)
    except LandingNotFoundError as exc:
        raise _not_found("Landing not found") from exc
    except BlockNotFoundError as exc:
        raise _not_found("Conversion component not found") from exc

    for key in removed_video_keys:
        with contextlib.suppress(Exception):
            await r2.delete(key)

    return await _block_list(landing_id)
