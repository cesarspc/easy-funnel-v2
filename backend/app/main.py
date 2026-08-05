"""FastAPI application factory and router wiring.

Keeps route handlers thin: this module wires middleware and routers only.
Business rules live in `app.domains` and `app.services`.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
from app.core.settings import Settings, get_settings
from app.db import connect_db, disconnect_db
from app.db.client import get_db
from app.services.admin_bootstrap_service import ensure_admin_user

_logger = logging.getLogger("app.bootstrap")


async def _bootstrap_admin(settings: Settings) -> None:
    """Provision the Administrator from `ADMIN_USERNAME` / `ADMIN_PASSWORD`.

    A no-op unless both variables are set. Never fatal: a bootstrap failure is
    logged and startup continues, because an already-provisioned deployment
    must not be taken offline by a problem creating an account it already has.
    """
    if not settings.admin_username or not settings.admin_password:
        _logger.info("ADMIN_USERNAME/ADMIN_PASSWORD not set; skipping admin bootstrap.")
        return

    try:
        outcome = await ensure_admin_user(
            get_db(),
            username=settings.admin_username,
            password=settings.admin_password,
            reset_existing=settings.admin_password_reset,
        )
        # Logs the username and outcome only — never the password or its hash.
        _logger.info("Admin bootstrap for '%s': %s.", settings.admin_username, outcome)
    except Exception:
        _logger.exception("Admin bootstrap failed; continuing startup.")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application instance."""
    configure_logging()
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await connect_db()
        await _bootstrap_admin(settings)
        try:
            yield
        finally:
            await disconnect_db()

    app = FastAPI(
        title="COD Commerce Platform API",
        version=os.getenv("APP_VERSION", "0.1.0"),
        lifespan=lifespan,
    )

    # CORS — parse comma-separated origins from CORS_ALLOWED_ORIGINS env var.
    allowed_origins = [
        origin.strip()
        for origin in settings.cors_allowed_origins.split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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
