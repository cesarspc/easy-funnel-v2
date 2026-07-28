"""Analytics domain: view/click recording and aggregation.

Implements Requirement 8.11-8.15:
- View/click recording (no contact fields)
- Per-day and per-landing aggregation
- Inclusive date-range resolution for dashboard queries
- Conversion rate with zero-guarded denominators
- Flagged-fraud rate computation
"""

from app.domains.analytics.date_range import DateRange, parse_date_range
from app.domains.analytics.errors import AnalyticsValidationError
from app.domains.analytics.models import (
    FraudAnalytics,
    LandingAnalytics,
    OrdersPerDay,
    OrdersPerLanding,
)
from app.domains.analytics.rates import conversion_rate, flagged_fraud_rate

__all__ = [
    "OrdersPerDay",
    "LandingAnalytics",
    "FraudAnalytics",
    "OrdersPerLanding",
    "AnalyticsValidationError",
    "DateRange",
    "parse_date_range",
    "conversion_rate",
    "flagged_fraud_rate",
]
