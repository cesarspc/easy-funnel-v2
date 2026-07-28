"""FastAPI routers and request-scoped dependencies.

Routers:
- auth: login, logout, session endpoints
- ops: health, version, jobs endpoints (operational read)
- products: product CRUD + lifecycle endpoints
- public: public landing + checkout endpoints
- admin_landings: landing config, banner upload/order, publication endpoints
- admin_orders: order management endpoints
- admin_fraud: fraud config/blacklist/geoip endpoints
- admin_analytics: analytics endpoints
"""

from app.api.routers import (
    admin_analytics,
    admin_fraud,
    admin_landings,
    admin_orders,
    auth,
    ops,
    products,
    public,
)

__all__ = [
    "auth",
    "ops",
    "products",
    "public",
    "admin_landings",
    "admin_orders",
    "admin_fraud",
    "admin_analytics",
]
