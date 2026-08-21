"""Admin Products API router: CRUD and lifecycle endpoints."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, status
from prisma import Json
from pydantic import BaseModel, Field

from app.core.auth_dependencies import require_admin
from app.core.settings import Settings
from app.db.client import get_prisma
from app.db.repositories import AuditLogRepository
from app.domains.products.errors import (
    DuplicateSkuError,
    ProductNotFoundError,
    ProductValidationError,
    RetiredProductError,
)
from app.domains.products.mastershop_mappings import validate_mastershop_mappings
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
    variant_options: list[dict] = Field(default_factory=list)


class ProductUpdateRequest(BaseModel):
    name: str | None = None
    sku: str | None = None
    price: Decimal | None = None
    description: str | None = None


class ProductResponse(BaseModel):
    id: int
    name: str
    sku: str
    price: float
    description: str
    status: str
    retired_at: str | None = None
    landing_id: int | None = None
    landing_slug: str | None = None
    landing_status: str | None = None
    variant_options: list[dict] = Field(default_factory=list)


def _to_product_response(product, landing=None) -> ProductResponse:  # type: ignore[no-untyped-def]
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
        landing_id=resolved_landing.id if resolved_landing else None,
        landing_slug=resolved_landing.slug if resolved_landing else None,
        landing_status=resolved_landing.status if resolved_landing else None,
        variant_options=(
            product.variantOptions
            if isinstance(getattr(product, "variantOptions", None), list)
            else []
        ),
    )


class ProductListResponse(BaseModel):
    products: list[ProductResponse]


class MastershopProductMappingRequest(BaseModel):
    variant_selection: dict[str, str] = Field(default_factory=dict)
    mastershop_product_id: int
    mastershop_variant_id: int | None = None
    weight: float = 1


class MastershopMappingsRequest(BaseModel):
    mappings: list[MastershopProductMappingRequest]


def _serialize_mastershop_mapping(mapping: Any) -> dict[str, Any]:
    return {
        "id": mapping.id,
        "variant_selection": mapping.variantSelection,
        "mastershop_product_id": mapping.mastershopProductId,
        "mastershop_variant_id": mapping.mastershopVariantId,
        "weight": float(mapping.weight),
    }


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    request: ProductCreateRequest,
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008
    settings: Settings = Depends(lambda: Settings()),  # type: ignore  # noqa: B008
):
    """Create a new product with an atomic draft landing."""
    db = get_prisma()

    service = ProductLifecycleService(db)
    try:
        result = await service.create_product(
            name=request.name,
            sku=request.sku,
            price=Decimal(str(request.price)),
            description=request.description,
            status=request.status,
            variant_options=request.variant_options,
            actor=admin_user.subject,
        )
    except ProductValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"field": exc.field, "message": exc.message},
        ) from exc
    except DuplicateSkuError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"field": "sku", "message": str(exc)},
        ) from exc

    return _to_product_response(result.product, landing=result.landing)


@router.get("", response_model=ProductListResponse)
async def list_products(
    include_retired: bool = False,
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008
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


@router.get("/{product_id}/mastershop-mappings", response_model=dict)
async def get_mastershop_mappings(
    product_id: int,
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008
):
    db = get_prisma()
    product = await db.product.find_unique(where={"id": product_id})
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    mappings = await db.mastershopproductmapping.find_many(
        where={"productId": product_id}, order={"id": "asc"}
    )
    return {"mappings": [_serialize_mastershop_mapping(mapping) for mapping in mappings]}


@router.put("/{product_id}/mastershop-mappings", response_model=dict)
async def replace_mastershop_mappings(
    product_id: int,
    request: MastershopMappingsRequest,
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008
):
    """Atomically replace the complete mapping matrix for one product."""
    db = get_prisma()
    product = await db.product.find_unique(where={"id": product_id})
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    options: list[dict[str, Any]] = (
        cast(list[dict[str, Any]], product.variantOptions)
        if isinstance(product.variantOptions, list)
        else []
    )
    try:
        validated = validate_mastershop_mappings(
            [mapping.model_dump() for mapping in request.mappings], options=options
        )
    except ProductValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"field": exc.field, "message": exc.message},
        ) from exc

    async with db.tx() as tx:
        await tx.mastershopproductmapping.delete_many(where={"productId": product_id})
        stored = []
        for mapping in validated:
            stored.append(
                await tx.mastershopproductmapping.create(
                    {
                        "productId": product_id,
                        "selectionKey": mapping["selection_key"],
                        "variantSelection": Json(mapping["variant_selection"]),
                        "mastershopProductId": mapping["mastershop_product_id"],
                        "mastershopVariantId": mapping["mastershop_variant_id"],
                        "weight": Decimal(str(mapping["weight"])),
                    }
                )
            )
        await AuditLogRepository(tx).record(
            actor=admin_user.subject,
            action="mastershop.product_mappings.replaced",
            target_type="product",
            target_id=str(product_id),
            result="success",
        )
    return {"mappings": [_serialize_mastershop_mapping(mapping) for mapping in stored]}


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: int,
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008
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
    request: ProductUpdateRequest,
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008
):
    """Validate and update supplied fields on a non-retired product."""
    db = get_prisma()
    raw = request.model_dump(exclude_unset=True)
    null_field = next((field for field, value in raw.items() if value is None), None)
    if null_field is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"field": null_field, "message": "This field cannot be null."},
        )
    updates = cast(dict[str, str | Decimal], raw)

    try:
        await ProductLifecycleService(db).update_product(
            product_id,
            updates=updates,
            actor=admin_user.subject,
        )
    except ProductValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"field": exc.field, "message": exc.message},
        ) from exc
    except DuplicateSkuError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"field": "sku", "message": str(exc)},
        ) from exc
    except ProductNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RetiredProductError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    updated = await db.product.find_unique(where={"id": product_id}, include={"landing": True})
    if updated is None:  # Defensive: the transaction above already established existence.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return _to_product_response(updated)


@router.post("/{product_id}/activate", response_model=ProductResponse)
async def activate_product(
    product_id: int,
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008
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

    with_landing = await db.product.find_unique(where={"id": product.id}, include={"landing": True})
    return _to_product_response(with_landing if with_landing else product)


@router.post("/{product_id}/pause", response_model=ProductResponse)
async def pause_product(
    product_id: int,
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008
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

    with_landing = await db.product.find_unique(where={"id": product.id}, include={"landing": True})
    return _to_product_response(with_landing if with_landing else product)


@router.delete("/{product_id}")
async def retire_product(
    product_id: int,
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008
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
