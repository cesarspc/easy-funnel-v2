"""Admin Products API router: CRUD + lifecycle endpoints (Requirement 2.1, 2.8, 2.9, 2.13, 2.17, 2.19-2.20)."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.auth_dependencies import require_admin
from app.core.settings import Settings
from app.db.client import get_prisma
from app.services.product_lifecycle_service import (
    ProductLifecycleService,
)

router = APIRouter(prefix="/api/admin/products", tags=["admin", "products"])


class ProductCreateRequest(BaseModel):
    name: str
    sku: str
    price: float
    description: str = ""
    status: str | None = None


class ProductResponse(BaseModel):
    id: int
    name: str
    sku: str
    price: float
    description: str
    status: str
    retired_at: str | None = None
    landing_slug: str | None = None
    landing_status: str | None = None


def _to_product_response(product, landing=None) -> "ProductResponse":  # type: ignore[no-untyped-def]
    """Build a ProductResponse, including the 1:1 Landing's slug/status.

    `landing` may be passed explicitly (e.g. from ProductCreationResult);
    otherwise it is read from `product.landing` when the caller's Prisma
    query included that relation.
    """
    resolved_landing = landing if landing is not None else getattr(product, "landing", None)
    return ProductResponse(
        id=product.id,
        name=product.name,
        sku=product.sku,
        price=float(product.price),
        description=product.description,
        status=product.status,
        retired_at=product.retiredAt.isoformat() if product.retiredAt else None,
        landing_slug=resolved_landing.slug if resolved_landing else None,
        landing_status=resolved_landing.status if resolved_landing else None,
    )


class ProductListResponse(BaseModel):
    products: list[ProductResponse]


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    request: ProductCreateRequest,
    admin_user=Depends(require_admin),  # type: ignore
    settings: Settings = Depends(lambda: Settings()),  # type: ignore
):
    """Create a new product with an atomic draft landing."""
    db = get_prisma()

    service = ProductLifecycleService(db)
    result = await service.create_product(
        name=request.name,
        sku=request.sku,
        price=Decimal(str(request.price)),
        description=request.description,
        status=request.status,
        actor=admin_user.subject,
    )

    return _to_product_response(result.product, landing=result.landing)


@router.get("", response_model=ProductListResponse)
async def list_products(
    include_retired: bool = False,
    admin_user=Depends(require_admin),  # type: ignore
):
    """List products, excluding retired by default."""
    db = get_prisma()

    if include_retired:
        products = await db.product.find_many(include={"landing": True})
    else:
        products = await db.product.find_many(
            where={"status": {"not": "retired"}}, include={"landing": True}
        )

    return ProductListResponse(products=[_to_product_response(p) for p in products])


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: int,
    admin_user=Depends(require_admin),  # type: ignore
):
    """Get a specific product."""
    db = get_prisma()
    product = await db.product.find_unique(where={"id": product_id}, include={"landing": True})

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    return _to_product_response(product)


@router.patch("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: int,
    request: ProductCreateRequest,
    admin_user=Depends(require_admin),  # type: ignore
):
    """Update a non-retired product."""
    db = get_prisma()
    product = await db.product.find_unique(where={"id": product_id})

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    if product.status == "retired":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot edit a retired product",
        )

    updated = await db.product.update(
        where={"id": product_id},
        data={
            "name": request.name,
            "description": request.description,
            "price": Decimal(str(request.price)),
            "sku": request.sku,
        },
        include={"landing": True},
    )

    return _to_product_response(updated)


@router.post("/{product_id}/activate", response_model=ProductResponse)
async def activate_product(
    product_id: int,
    admin_user=Depends(require_admin),  # type: ignore
):
    """Activate a paused product."""
    db = get_prisma()
    service = ProductLifecycleService(db)

    try:
        product = await service.activate(product_id, actor=admin_user.subject)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    with_landing = await db.product.find_unique(
        where={"id": product.id}, include={"landing": True}
    )
    return _to_product_response(with_landing if with_landing else product)


@router.post("/{product_id}/pause", response_model=ProductResponse)
async def pause_product(
    product_id: int,
    admin_user=Depends(require_admin),  # type: ignore
):
    """Pause an active product."""
    db = get_prisma()
    service = ProductLifecycleService(db)

    try:
        product = await service.pause(product_id, actor=admin_user.subject)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    with_landing = await db.product.find_unique(
        where={"id": product.id}, include={"landing": True}
    )
    return _to_product_response(with_landing if with_landing else product)


@router.delete("/{product_id}")
async def retire_product(
    product_id: int,
    admin_user=Depends(require_admin),  # type: ignore
):
    """Soft-delete (retire) a product."""
    db = get_prisma()
    service = ProductLifecycleService(db)

    try:
        await service.retire(product_id, actor=admin_user.subject)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return {"message": "Product retired successfully"}
