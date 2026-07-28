"""FastAPI application factory and router wiring.

Keeps route handlers thin: this module wires middleware and routers only.
Business rules live in `app.domains` and `app.services`.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

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
from app.core import configure_logging
from app.db import connect_db, disconnect_db


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application instance."""
    configure_logging()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await connect_db()
        try:
            yield
        finally:
            await disconnect_db()

    app = FastAPI(
        title="COD Commerce Platform API",
        version=os.getenv("APP_VERSION", "0.1.0"),
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Liveness endpoint used by the Koyeb health check."""
        return {"status": "healthy", "version": app.version}

    # Wire routers
    app.include_router(auth.router)
    app.include_router(ops.router)
    app.include_router(products.router)
    app.include_router(public.router)
    app.include_router(admin_landings.router)
    app.include_router(admin_orders.router)
    app.include_router(admin_fraud.router)
    app.include_router(admin_analytics.router)

    return app


app = create_app()
