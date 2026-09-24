"""Admin Analytics API router: orders-per-day, landings, fraud endpoints.

Requirements 8.11-8.13, 8.21, 10.9. Thin layer over `AnalyticsQueryService`:
the inclusive date range is resolved by `app.domains.analytics.date_range`, and
a malformed or inverted range is a field-specific `422` rather than an
unhandled parse failure.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from redis.asyncio import Redis as AsyncRedis

from app.core.auth_dependencies import require_admin
from app.db.client import get_prisma
from app.domains.analytics.date_range import parse_date_range
from app.domains.analytics.errors import AnalyticsValidationError
from app.redis.client import get_redis
from app.services.analytics_query_service import AnalyticsQueryService
from app.services.platform_config import load_platform_config

router = APIRouter(prefix="/api/admin/analytics", tags=["admin", "analytics"])


class OrdersPerDayResponse(BaseModel):
    date: str
    count: int


class LandingAnalyticsResponse(BaseModel):
    landing_id: int
    views: int
    clicks: int
    orders: int
    conversion_rate: float


class FraudAnalyticsResponse(BaseModel):
    date: str
    flagged_orders: int
    total_orders: int
    flagged_fraud_rate: float


async def _resolve_range(date_from: str, date_to: str):  # type: ignore[no-untyped-def]
    time_zone = (await load_platform_config(get_prisma())).regional.time_zone
    try:
        return parse_date_range(date_from, date_to, time_zone)
    except AnalyticsValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"field": exc.field, "message": exc.message},
        ) from exc


@router.get("/orders-per-day", response_model=list[OrdersPerDayResponse])
async def get_orders_per_day(
    date_from: str = Query(...),
    date_to: str = Query(...),
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> list[OrdersPerDayResponse]:
    """Return orders per calendar day for the inclusive range."""
    date_range = await _resolve_range(date_from, date_to)
    results = await AnalyticsQueryService(get_prisma()).get_orders_per_day(date_range)

    return [
        OrdersPerDayResponse(date=result.date.isoformat(), count=result.count) for result in results
    ]


@router.get("/landings", response_model=list[LandingAnalyticsResponse])
async def get_landing_analytics(
    date_from: str = Query(...),
    date_to: str = Query(...),
    landing_id: int | None = Query(None),
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
    redis: AsyncRedis = Depends(get_redis),  # noqa: B008 (FastAPI DI)
) -> list[LandingAnalyticsResponse]:
    """Return per-landing views, clicks, orders, and conversion rate."""
    date_range = await _resolve_range(date_from, date_to)
    results = await AnalyticsQueryService(get_prisma(), redis).get_landing_analytics(
        date_range, landing_id=landing_id
    )

    return [
        LandingAnalyticsResponse(
            landing_id=result.landing_id,
            views=result.views,
            clicks=result.clicks,
            orders=result.orders,
            conversion_rate=result.conversion_rate,
        )
        for result in results
    ]


@router.get("/fraud", response_model=list[FraudAnalyticsResponse])
async def get_fraud_analytics(
    date_from: str = Query(...),
    date_to: str = Query(...),
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> list[FraudAnalyticsResponse]:
    """Return per-day flagged-order counts and flagged-fraud rate."""
    date_range = await _resolve_range(date_from, date_to)
    results = await AnalyticsQueryService(get_prisma()).get_fraud_analytics(date_range)

    return [
        FraudAnalyticsResponse(
            date=result.date.isoformat(),
            flagged_orders=result.flagged_orders,
            total_orders=result.total_orders,
            flagged_fraud_rate=result.flagged_fraud_rate,
        )
        for result in results
    ]
