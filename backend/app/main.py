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

from app.api.openapi import API_TITLE, build_openapi
from app.api.routers import (
    admin_analytics,
    admin_fraud,
    admin_landing_templates,
    admin_landings,
    admin_orders,
    auth,
    ops,
    products,
    public,
    store,
)
from app.core import configure_logging
from app.core.settings import Settings, get_settings
from app.db import connect_db, disconnect_db
from app.db.client import get_db
from app.services.admin_bootstrap_service import ensure_admin_user
from app.services.store_settings_service import ensure_store_settings

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
        await ensure_store_settings(get_db(), settings)
        try:
            yield
        finally:
            await disconnect_db()

    app = FastAPI(
        title=API_TITLE,
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

    @app.get("/health", tags=["ops"], summary="Liveness probe")
    async def health() -> dict[str, str]:
        """Report that the process is up, with the deployed version.

        Answers without touching PostgreSQL, Redis or object storage, so a
        container orchestrator can tell "the process is alive" apart from "its
        dependencies are reachable" — the latter is
        `GET /api/admin/ops/health`.
        """
        return {"status": "healthy", "version": app.version}

    # Wire routers
    app.include_router(auth.router)
    app.include_router(ops.router)
    app.include_router(products.router)
    app.include_router(public.router)
    app.include_router(store.public_router)
    app.include_router(store.admin_router)
    app.include_router(admin_landings.router)
    app.include_router(admin_landing_templates.router)
    app.include_router(admin_orders.router)
    app.include_router(admin_fraud.router)
    app.include_router(admin_analytics.router)

    # Metadata, security scheme and tag descriptions are layered on top of the
    # generated document; see `app/api/openapi.py`.
    app.openapi = lambda: build_openapi(app)  # type: ignore[method-assign]

    return app


app = create_app()
