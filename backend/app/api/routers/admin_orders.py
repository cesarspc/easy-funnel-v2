"""Admin Orders API router: list, detail, transition, export endpoints.

Requirements 5.19-5.22, 8.4-8.10, 8.16.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.core.auth_dependencies import require_admin
from app.db.client import get_prisma

router = APIRouter(prefix="/api/admin/orders", tags=["admin", "orders"])


def _serialize_order(order, *, include_flags: bool = False) -> dict:
    """Map a persisted order onto the documented admin JSON shape.

    Prisma models never cross the API boundary (Requirement 10.3, design.md ->
    db): the router returns plain snake_case payloads matching the admin API
    contract the SPA consumes (`frontend/src/api/admin.ts`).
    """
    payload: dict[str, Any] = {
        "id": order.id,
        "product_id": order.productId,
        "landing_id": order.landingId,
        "landing_slug": order.landingSlug,
        "customer_name": order.customerName,
        "phone_e164": order.phoneE164,
        "phone_normalized_key": order.phoneNormalizedKey,
        "department": order.department,
        "city": order.city,
        "address": order.address,
        "quantity": order.quantity,
        "variant_selections": (
            order.variantSelections
            if isinstance(getattr(order, "variantSelections", None), list)
            else []
        ),
        "unit_price": float(order.unitPrice),
        "discount_percent": order.discountPercent,
        "total_price": float(order.totalPrice),
        "status": order.status,
        "ip_address": order.ipAddress,
        "user_agent": order.userAgent,
        "created_at": order.createdAt.isoformat(),
        "updated_at": order.updatedAt.isoformat(),
    }
    product = getattr(order, "product", None)
    if product is not None:
        payload["product_name"] = product.name
        payload["product_sku"] = product.sku
    if include_flags:
        payload["fraud_flags"] = [
            {
                "id": flag.id,
                "flag_type": flag.flagType,
                "detail": flag.detail,
                "created_at": flag.createdAt.isoformat(),
            }
            for flag in (order.fraudFlags or [])
        ]
    return payload


@router.get("", response_model=dict)
async def list_orders(
    status: str | None = Query(None),
    product_id: int | None = Query(None),
    landing_id: int | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    admin_user=Depends(require_admin),  # type: ignore # noqa: B008 (FastAPI DI)
):
    """List orders with filters (ANDed together)."""
    db = get_prisma()

    where: dict[str, Any] = {}

    if status:
        where["status"] = status

    if product_id:
        where["productId"] = product_id

    if landing_id:
        where["landingId"] = landing_id

    if date_from or date_to:
        where["createdAt"] = {}
        if date_from:
            where["createdAt"]["gte"] = datetime.fromisoformat(date_from)
        if date_to:
            where["createdAt"]["lte"] = datetime.fromisoformat(date_to)

    orders = await db.order.find_many(
        where=cast(Any, where),
        order={"createdAt": "desc"},
    )

    return {
        "orders": [_serialize_order(order) for order in orders],
        "count": len(orders),
    }


class OrderTransitionRequest(BaseModel):
    to_status: str


# Declared before `/{order_id}` so the literal export path is matched first;
# otherwise FastAPI routes `export.csv` into the int path parameter and the
# request fails validation instead of exporting.
@router.get("/export.csv")
async def export_orders_csv(
    status: str | None = Query(None),
    product_id: int | None = Query(None),
    landing_id: int | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    admin_user=Depends(require_admin),  # type: ignore # noqa: B008 (FastAPI DI)
):
    """Export orders to CSV with formula-injection neutralization."""
    from app.services.csv_export_service import CsvExportService

    db = get_prisma()

    where: dict[str, Any] = {}
    if status:
        where["status"] = status
    if product_id:
        where["productId"] = product_id
    if landing_id:
        where["landingId"] = landing_id
    if date_from or date_to:
        where["createdAt"] = {}
        if date_from:
            where["createdAt"]["gte"] = datetime.fromisoformat(date_from)
        if date_to:
            where["createdAt"]["lte"] = datetime.fromisoformat(date_to)

    orders = await db.order.find_many(
        where=cast(Any, where),
        include={"fraudFlags": True},
        order={"createdAt": "desc"},
    )

    order_list = [
        {
            **_serialize_order(order, include_flags=True),
            "created_at": order.createdAt,
            "updated_at": order.updatedAt,
        }
        for order in orders
    ]

    service = CsvExportService()
    csv_content = service.export_orders(orders=order_list)

    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=orders.csv"},
    )


@router.get("/{order_id}", response_model=dict)
async def get_order(
    order_id: int,
    admin_user=Depends(require_admin),  # type: ignore # noqa: B008 (FastAPI DI)
):
    """Get order detail with fraud flags."""
    db = get_prisma()

    order = await db.order.find_unique(
        where={"id": order_id},
        include={"fraudFlags": True, "product": True},
    )

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    return _serialize_order(order, include_flags=True)


@router.post("/{order_id}/transition")
async def transition_order(
    order_id: int,
    request: OrderTransitionRequest,
    admin_user=Depends(require_admin),  # type: ignore # noqa: B008 (FastAPI DI)
):
    """Transition order status (legal graph only)."""
    db = get_prisma()

    order = await db.order.find_unique(where={"id": order_id})

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    from app.domains.orders import InvalidOrderStatusTransition, validate_status

    try:
        validate_status(order.status, request.to_status)
    except InvalidOrderStatusTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    updated = await db.order.update(
        where={"id": order_id},
        data={"status": request.to_status},
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    return {"order_id": updated.id, "status": updated.status}
