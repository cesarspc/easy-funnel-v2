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
from app.domains.landings.cta_placement import compute_cta_positions, validate_cta_config
from app.domains.landings.errors import (
    BannerLimitExceededError,
    BannerNotFoundError,
    DuplicateSlugError,
    LandingNotFoundError,
    LandingValidationError,
    PublicationValidationError,
)
from app.services.banner_upload_service import BannerUploadService
from app.services.landing_management_service import LandingManagementService
from app.services.landing_publication_service import LandingPublicationService
from app.storage.dependencies import get_r2_client
from app.storage.r2_client import R2Client, variant_public_url

router = APIRouter(prefix="/api/admin/landings", tags=["admin", "landings"])

_UPLOAD_UNAVAILABLE_MESSAGE = "Image upload is temporarily unavailable. Please try again."


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
    banner_count: int


class LandingListResponse(BaseModel):
    landings: list[LandingSummaryResponse]


class LandingDetailResponse(LandingSummaryResponse):
    banners: list[BannerResponse]
    resolved_cta_positions: list[int]


class BannerListResponse(BaseModel):
    banners: list[BannerResponse]


class LandingConfigUpdateRequest(BaseModel):
    slug: str | None = None
    cta_mode: str | None = None
    cta_interval: int | None = None
    cta_positions: list[int] | None = None
    form_presentation: str | None = None
    cta_band_style: str | None = None


class BannerUpdateRequest(BaseModel):
    alt_text: str | None = None
    order_index: int | None = None


class BannerOrderRequest(BaseModel):
    banner_ids: list[int]


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
        banner_count=len(banners),
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
    """Update slug, CTA configuration/band style, and COD form presentation."""
    db = get_prisma()
    service = LandingManagementService(db)

    try:
        await service.update_config(
            landing_id,
            slug=request.slug,
            cta_mode=request.cta_mode,
            cta_interval=request.cta_interval,
            cta_positions=request.cta_positions,
            form_presentation=request.form_presentation,
            cta_band_style=request.cta_band_style,
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
