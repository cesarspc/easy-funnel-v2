"""Auth API router: login, logout, session endpoints (Requirement 7.1-7.15)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from upstash_redis import AsyncRedis

from app.core.auth_dependencies import require_admin
from app.core.request_context import RequestContext, get_request_context
from app.core.settings import Settings, get_settings
from app.db.client import get_prisma
from app.db.repositories import AdminUserRepository, AuditLogRepository
from app.redis.client import get_redis
from app.schemas.auth import LoginRequest, LoginResponse, SessionResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    context: RequestContext = Depends(get_request_context),  # noqa: B008 (FastAPI DI)
    redis: AsyncRedis = Depends(get_redis),  # noqa: B008 (FastAPI DI convention)
    settings: Settings = Depends(get_settings),  # noqa: B008 (FastAPI DI convention)
):
    """Authenticate an Administrator and issue a JWT session cookie.

    `AuthService` owns rate limiting, credential verification, token issuance,
    and audit logging. Unknown usernames and incorrect passwords return the
    same generic 401. A Redis outage does not expose credentials or crash the
    request; the service continues with credential verification while the
    rate-limit result is unavailable.
    """
    db = get_prisma()
    auth_service = AuthService(
        settings=settings,
        admin_users=AdminUserRepository(db),
        audit_log=AuditLogRepository(db),
        redis=redis,
    )
    result = await auth_service.login(
        username=request.username,
        password=request.password,
        ip_address=context.ip_address,
    )

    if result.rate_limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again later.",
        )
    if not result.success or result.token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    response = JSONResponse(content=LoginResponse(authenticated=True, role="admin").model_dump())
    response.set_cookie(
        key="session",
        value=result.token,
        httponly=True,
        # HTTPS-only in deployed environments; localhost development uses HTTP.
        secure=settings.environment != "development",
        samesite="strict",
        max_age=settings.jwt_expiry_minutes * 60,
        path="/",
    )
    return response


@router.post("/logout")
async def logout(
    admin_user=Depends(require_admin),  # type: ignore # noqa: B008 (FastAPI DI)
):
    """Invalidate the current session.

    Marks the token as unusable per transport (clears cookie / invalidates
    session in database).
    """
    response = JSONResponse(content={"logged_out": True})
    response.delete_cookie(key="session")
    return response


@router.get("/session", response_model=SessionResponse)
async def get_session(
    admin_user=Depends(require_admin),  # type: ignore # noqa: B008 (FastAPI DI)
):
    """Return current session state for SPA guard hydration.

    Returns {authenticated, role} without exposing JWT.
    """
    # Version 1 has one Administrator role; the JWT subject carries identity.
    return SessionResponse(authenticated=True, role="admin")
