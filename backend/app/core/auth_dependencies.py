"""FastAPI dependencies for Administrator session authorization.

`require_admin` is the dependency every private (`/api/admin/*`,
`/api/admin/ops/*`) router uses to authorize a request (Requirement 7.3).
Every rejection path — missing token, expired, tampered, wrong
issuer/audience/algorithm — raises the same generic 401 so no distinguishing
detail leaks to the caller (Requirement 7.4).
"""

from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, Request, status

from app.core.jwt_auth import AdminSession, validate_token
from app.core.settings import Settings, get_settings

_SESSION_COOKIE_NAME = "session"
_GENERIC_AUTH_ERROR = "Authentication required."


def _extract_token(request: Request) -> str | None:
    """Read the session token from the preferred cookie transport, with a
    bearer-header fallback for non-browser/API clients."""
    cookie_token = request.cookies.get(_SESSION_COOKIE_NAME)
    if cookie_token:
        return cookie_token

    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[len("Bearer ") :].strip()

    return None


def require_admin(
    request: Request,
    settings: Settings = Depends(get_settings),  # noqa: B008 (FastAPI DI convention)
) -> AdminSession:
    """Authorize the current request for the Administrator role.

    Raises `HTTPException(401)` with a generic message for every failure
    mode: missing token, expired, tampered, or otherwise invalid.
    """
    token = _extract_token(request)
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC_AUTH_ERROR)

    try:
        return validate_token(settings, token)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC_AUTH_ERROR
        ) from exc
