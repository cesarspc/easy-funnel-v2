"""Analytics domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class OrdersPerDay:
    """Orders per calendar day."""

    date: date
    count: int


@dataclass(frozen=True)
class LandingAnalytics:
    """Per-landing analytics for a date range."""

    landing_id: int
    views: int
    clicks: int
    orders: int
    conversion_rate: float


@dataclass(frozen=True)
class FraudAnalytics:
    """Per-day fraud analytics."""

    date: date
    flagged_orders: int
    total_orders: int
    flagged_fraud_rate: float


@dataclass(frozen=True)
class OrdersPerLanding:
    """Per-landing order count."""

    landing_id: int
    landing_slug: str
    order_count: int
