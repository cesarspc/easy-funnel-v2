"""Admin Orders API router: list, detail, transition, export endpoints.

Requirements 5.19-5.22, 8.4-8.10, 8.16.
"""

from __future__ import annotations

from contextlib import suppress
from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from prisma import Json
from pydantic import BaseModel

from app.core.auth_dependencies import require_admin
from app.db.client import get_prisma
from app.db.repositories import AuditLogRepository, FraudConfigRepository
from app.domains.orders import (
    OrderValidationError,
    normalize_colombian_phone,
    normalize_colombian_phone_key,
    validate_address,
    validate_name,
)
from app.domains.orders.locations import validate_delivery_location

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
    details = getattr(order, "fulfillmentDetails", None)
    payload["fulfillment_details"] = (
        {
            "first_name": details.firstName,
            "last_name": details.lastName,
            "address1": details.address1,
            "address2": details.address2,
        }
        if details is not None
        else None
    )
    sync = getattr(order, "mastershopSync", None)
    payload["mastershop_sync"] = _serialize_mastershop_sync(sync) if sync is not None else None
    return payload


def _serialize_mastershop_sync(sync) -> dict:  # type: ignore[no-untyped-def]
    return {
        "status": sync.status,
        "attempt_count": sync.attemptCount,
        "response_status": sync.responseStatus,
        "response_body": sync.responseBody,
        "last_error": sync.lastError,
        "last_attempt_at": sync.lastAttemptAt.isoformat() if sync.lastAttemptAt else None,
        "synced_at": sync.syncedAt.isoformat() if sync.syncedAt else None,
        "updated_at": sync.updatedAt.isoformat(),
    }


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
        include={"mastershopSync": True},
        order={"createdAt": "desc"},
    )

    return {
        "orders": [_serialize_order(order) for order in orders],
        "count": len(orders),
    }


class OrderTransitionRequest(BaseModel):
    to_status: str


class OrderFulfillmentUpdateRequest(BaseModel):
    first_name: str
    last_name: str
    phone: str
    department: str
    city: str
    address1: str
    address2: str | None = None


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
        include={
            "fraudFlags": True,
            "product": True,
            "fulfillmentDetails": True,
            "mastershopSync": True,
        },
    )

    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    return _serialize_order(order, include_flags=True)


@router.patch("/{order_id}/fulfillment", response_model=dict)
async def update_order_fulfillment(
    order_id: int,
    request: OrderFulfillmentUpdateRequest,
    admin_user=Depends(require_admin),  # type: ignore # noqa: B008 (FastAPI DI)
):
    """Edit delivery data before a successful external synchronization."""
    db = get_prisma()
    order = await db.order.find_unique(where={"id": order_id}, include={"mastershopSync": True})
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    sync = order.mastershopSync
    if sync is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This historical order is not enrolled in MasterShop synchronization.",
        )
    if sync.status in {"success", "syncing"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A synchronized or in-progress MasterShop order cannot be edited.",
        )

    try:
        first_name = request.first_name.strip()
        last_name = request.last_name.strip()
        if not first_name:
            raise OrderValidationError("first_name", "First name is required.")
        if not last_name:
            raise OrderValidationError("last_name", "Last name is required.")
        full_name = validate_name(f"{first_name} {last_name}")
        phone_e164 = normalize_colombian_phone(request.phone)
        phone_key = normalize_colombian_phone_key(request.phone)
        address1 = request.address1.strip()
        if not address1:
            raise OrderValidationError("address1", "Address line 1 is required.")
        address2 = request.address2.strip() if request.address2 else None
        full_address = validate_address(" ".join(part for part in [address1, address2] if part))
        config = await FraudConfigRepository(db).get()
        department, city = validate_delivery_location(
            request.department,
            request.city,
            banned_cities=list(getattr(config, "bannedCities", None) or []) if config else [],
        )
    except OrderValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"field": exc.field, "message": exc.message},
        ) from exc

    next_sync_status = "pending" if order.status == "pending" else "waiting_review"
    async with db.tx() as tx:
        claimed = await tx.mastershopordersync.update_many(
            where={
                "orderId": order_id,
                "status": {"in": ["pending", "failed", "waiting_review"]},
            },
            # The temporary state prevents a sync worker from reading a
            # half-edited order. It is reset in this same transaction.
            data={"status": "syncing"},
        )
        if claimed == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The MasterShop order was synchronized or changed concurrently.",
            )
        await tx.order.update(
            where={"id": order_id},
            data={
                "customerName": full_name,
                "phoneE164": phone_e164,
                "phoneNormalizedKey": phone_key,
                "department": department,
                "city": city,
                "address": full_address,
            },
        )
        await tx.orderfulfillmentdetails.upsert(
            where={"orderId": order_id},
            data={
                "create": {
                    "orderId": order_id,
                    "firstName": first_name,
                    "lastName": last_name,
                    "address1": address1,
                    "address2": address2,
                },
                "update": {
                    "firstName": first_name,
                    "lastName": last_name,
                    "address1": address1,
                    "address2": address2,
                },
            },
        )
        await tx.mastershopordersync.update(
            where={"orderId": order_id},
            data={
                "status": next_sync_status,
                "requestBody": Json(None),
                "responseStatus": None,
                "responseBody": Json(None),
                "lastError": None,
                "syncedAt": None,
            },
        )
        await AuditLogRepository(tx).record(
            actor=admin_user.subject,
            action="order.fulfillment.updated",
            target_type="order",
            target_id=str(order_id),
            result="success",
        )

    updated = await db.order.find_unique(
        where={"id": order_id},
        include={
            "fraudFlags": True,
            "product": True,
            "fulfillmentDetails": True,
            "mastershopSync": True,
        },
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return _serialize_order(updated, include_flags=True)


@router.post(
    "/{order_id}/mastershop/retry",
    response_model=dict,
    summary="Retry a failed fulfillment hand-off",
)
async def retry_mastershop_sync(
    order_id: int,
    admin_user=Depends(require_admin),  # type: ignore # noqa: B008 (FastAPI DI)
):
    """Re-attempt the fulfillment provider hand-off for one order.

    The hand-off runs after an order is committed locally, so a provider outage
    or a missing product mapping leaves the order intact and the failure recorded
    on a durable sync row. This endpoint replays that hand-off and returns the
    resulting sync state.

    Safe to call repeatedly: an order that already synced is not sent twice.
    Inert while `FULFILLMENT_PROVIDER` is `none`.
    """
    from app.core.settings import get_settings
    from app.integrations.mastershop import MastershopSyncService

    db = get_prisma()
    try:
        sync = await MastershopSyncService(db, get_settings()).sync_order(order_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await AuditLogRepository(db).record(
        actor=admin_user.subject,
        action="mastershop.order_sync.retried",
        target_type="order",
        target_id=str(order_id),
        result=sync.status,
    )
    return {"order_id": order_id, "mastershop_sync": _serialize_mastershop_sync(sync)}


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

    if order.status == "flagged_fraud" and updated.status == "pending":
        from app.core.settings import get_settings
        from app.integrations.mastershop import MastershopSyncService

        with suppress(Exception):
            await MastershopSyncService(db, get_settings()).sync_order(updated.id)

    return {"order_id": updated.id, "status": updated.status}
