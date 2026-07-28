"""Dashboard rate computation with zero-guarded denominators (Requirement 8.21).

Both rates are ratios of counts over the same selected period:

- Conversion_Rate = Orders attributed to a Landing / recorded views for that
  Landing, expressed as zero when the view count is zero (Requirement 8.12,
  and the Conversion_Rate definition in requirements.md -> Definitions).
- Flagged_Fraud_Rate = Flagged_Orders / Orders, expressed as zero when the
  order count is zero (Requirement 8.13).
"""

from __future__ import annotations


def conversion_rate(*, orders: int, views: int) -> float:
    """Return orders divided by views, or 0.0 when there are no views."""
    if views <= 0:
        return 0.0
    return orders / views


def flagged_fraud_rate(*, flagged_orders: int, total_orders: int) -> float:
    """Return flagged orders divided by total orders, or 0.0 when there are none."""
    if total_orders <= 0:
        return 0.0
    return flagged_orders / total_orders
