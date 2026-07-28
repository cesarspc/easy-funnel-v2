"""Public landing and checkout API routers.

Requirements 3.21-3.24, 5.7-5.8, 5.13-5.17, 8.14-8.15.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from upstash_redis import AsyncRedis

from app.core.request_context import RequestContext, get_request_context
from app.core.settings import Settings, get_settings
from app.db.client import get_prisma
from app.domains.landings.cta_background import (
    BannerEdges,
    compute_cta_backgrounds,
)
from app.domains.orders.errors import OrderValidationError
from app.redis.client import get_redis
from app.services.geoip_resolver import GeoIpResolver, get_geoip_resolver
from app.services.order_submission_service import OrderSubmissionService
from app.storage.r2_client import variant_public_url

router = APIRouter(prefix="/api/public", tags=["public"])


class ImageVariantResponse(BaseModel):
    width: int
    height: int
    format: str
    url: str


class BannerResponse(BaseModel):
    id: int
    alt_text: str
    order_index: int
    variants: list[ImageVariantResponse]
    # Precomputed at upload; `None` when the edge is not usable as a flat
    # color (see app/domains/images/edge_color.py).
    top_edge_color: str | None = None
    bottom_edge_color: str | None = None


class CtaBackgroundResponse(BaseModel):
    """Background for the CTA rendered after 1-based banner `position`."""

    position: int
    top_color: str | None = None
    bottom_color: str | None = None
    blend_color: str | None = None
    foreground: str | None = None
    source: str


class LandingResponse(BaseModel):
    landing_id: int
    product_id: int
    product_name: str
    product_sku: str
    product_price: float
    slug: str
    banners: list[BannerResponse]
    cta_positions: list[int]
    cta_backgrounds: list[CtaBackgroundResponse]
    form_presentation: str
    # How the client paints the bands above: `gradient` (fade between the two
    # neighbouring edges) or `solid` (one flat color, the midpoint of them).
    # The colors themselves are identical either way.
    cta_band_style: str


@router.get("/landings/{slug}", response_model=LandingResponse)
async def get_public_landing(
    slug: str,
    settings: Settings = Depends(get_settings),  # noqa: B008 (FastAPI DI convention)
) -> LandingResponse:
    """Return landing payload for public display.

    Returns identical 404 for unknown, draft, paused, or retired slugs
    (no information disclosure).
    """
    db = get_prisma()

    landing = await db.landing.find_unique(
        where={"slug": slug},
        include={
            "product": True,
            "banners": {
                "include": {
                    "imageAsset": {
                        "include": {"variants": True},
                    }
                }
            },
        },
    )

    if landing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Landing not found",
        )

    product = landing.product
    stored_banners = landing.banners or []

    # Check product is active and landing is published. Missing included
    # relations are treated as the same generic unavailable state rather than
    # becoming an internal server error.
    if product is None or product.status != "active":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Landing not found",
        )

    if landing.status != "published":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Landing not found",
        )

    # Build banner response with R2 URLs
    from app.domains.landings.cta_placement import (
        compute_cta_positions,
        validate_cta_config,
    )

    cta_config = validate_cta_config(
        mode=landing.ctaMode,
        interval=landing.ctaInterval,
        positions=landing.ctaPositions,
    )
    cta_positions = compute_cta_positions(cta_config, len(stored_banners))

    public_host = settings.r2_public_host.rstrip("/")
    banners: list[BannerResponse] = []
    banner_edges: list[BannerEdges] = []
    for banner in sorted(stored_banners, key=lambda item: item.orderIndex):
        image_asset = banner.imageAsset
        if image_asset is None or image_asset.status != "complete":
            continue

        # Prisma relations are opt-in: the query above must nested-include
        # `variants`. `or []` remains defensive for legacy/malformed rows so a
        # public request never becomes a 500 solely because candidates are
        # absent.
        variants: list[ImageVariantResponse] = []
        stored_variants = sorted(
            image_asset.variants or [],
            key=lambda item: (item.width, item.format),
        )
        for variant in stored_variants:
            variants.append(
                ImageVariantResponse(
                    width=variant.width,
                    height=variant.height,
                    format=variant.format,
                    url=variant_public_url(
                        public_host,
                        image_asset.opaqueKey,
                        variant.width,
                        variant.format,
                    ),
                )
            )

        # An edge is offered whenever it was extracted. `*_edge_flat` is not
        # consulted: the strip mean is the least-wrong single color for that
        # edge by construction, so suppressing it in favour of the client's
        # neutral can only fit worse (see docs/backend.md, Banner Edge Colors
        # and CTA Bands).
        top_edge_color = image_asset.topEdgeColor
        bottom_edge_color = image_asset.bottomEdgeColor

        banners.append(
            BannerResponse(
                id=banner.id,
                alt_text=banner.altText,
                order_index=banner.orderIndex,
                variants=variants,
                top_edge_color=top_edge_color,
                bottom_edge_color=bottom_edge_color,
            )
        )
        # Positioned by render order, matching the 1-based CTA positions.
        banner_edges.append(BannerEdges(top=top_edge_color, bottom=bottom_edge_color))

    cta_backgrounds = [
        CtaBackgroundResponse(
            position=band.position,
            top_color=band.top_color,
            bottom_color=band.bottom_color,
            blend_color=band.blend_color,
            foreground=band.foreground,
            source=band.source,
        )
        for band in compute_cta_backgrounds(cta_positions, banner_edges)
    ]

    return LandingResponse(
        landing_id=landing.id,
        product_id=product.id,
        product_name=product.name,
        product_sku=product.sku,
        product_price=float(product.price),
        slug=landing.slug,
        banners=banners,
        cta_positions=cta_positions,
        cta_backgrounds=cta_backgrounds,
        form_presentation=landing.formPresentation,
        cta_band_style=landing.ctaBandStyle,
    )


class ViewRequest(BaseModel):
    landing_slug: str


@router.post("/landings/{slug}/view")
async def record_landing_view(
    slug: str,
    request: ViewRequest,
) -> dict[str, bool]:
    """Record a landing view (no contact fields)."""
    db = get_prisma()

    landing = await db.landing.find_unique(where={"slug": slug})
    if landing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Landing not found",
        )

    await db.landingview.create(data={"landingId": landing.id})
    return {"view_recorded": True}


@router.post("/landings/{slug}/cta-click")
async def record_cta_click(
    slug: str,
) -> dict[str, bool]:
    """Record a CTA click."""
    db = get_prisma()

    landing = await db.landing.find_unique(where={"slug": slug})
    if landing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Landing not found",
        )

    await db.ctaclick.create(data={"landingId": landing.id})
    return {"click_recorded": True}


class OrderCreateRequest(BaseModel):
    landing_slug: str
    full_name: str
    phone: str
    department: str
    city: str
    address: str
    quantity: int


class OrderCreateResponse(BaseModel):
    order_id: int
    status: str


@router.post(
    "/orders",
    response_model=OrderCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_order(
    request: OrderCreateRequest,
    context: RequestContext = Depends(get_request_context),  # noqa: B008 (FastAPI DI)
    redis: AsyncRedis = Depends(get_redis),  # noqa: B008 (FastAPI DI)
    geoip: GeoIpResolver = Depends(get_geoip_resolver),  # noqa: B008 (FastAPI DI)
) -> OrderCreateResponse:
    """Submit a COD order with fraud evaluation.

    The request IP address and user agent are taken from the trusted
    edge-forwarded request headers (Requirement 5.9-5.11), never from
    client-supplied body or query values.

    Returns 201 on persisted result, 422 on validation error,
    503 on persistence failure (no partial order).
    """
    db = get_prisma()
    service = OrderSubmissionService(db, redis, geoip)

    try:
        result = await service.submit(
            landing_slug=request.landing_slug,
            full_name=request.full_name,
            phone=request.phone,
            department=request.department,
            city=request.city,
            address=request.address,
            quantity=request.quantity,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            actor="system",
        )
        return OrderCreateResponse(order_id=result.order_id, status=result.status)
    except OrderValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"field": exc.field, "message": exc.message},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Order submission failed",
        ) from exc
