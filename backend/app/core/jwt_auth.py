"""JWT issuance and validation for Administrator sessions (Requirements 7.1, 7.3, 7.4).

Tokens carry issued-at, expiry, issuer, audience, and the Administrator
identity (subject). Validation is strict: the expected algorithm is always
passed explicitly to `jwt.decode` as an allowlist (never trusting the
token's own `alg` header), so an `alg: none` or algorithm-confusion attempt
is rejected the same as an expired or tampered signature — every failure
raises `InvalidTokenError` (or a subclass) so callers can return one
generic authentication error without distinguishing which check failed
(Requirement 7.4).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.core.settings import Settings


@dataclass(frozen=True)
class AdminSession:
    """Decoded, validated Administrator session claims."""

    subject: str
    issued_at: datetime
    expires_at: datetime


def issue_token(settings: Settings, *, subject: str, now: datetime | None = None) -> str:
    """Issue a signed JWT for the given Administrator identity (`subject`)."""
    issued_at = now or datetime.now(UTC)
    expires_at = issued_at + timedelta(minutes=settings.jwt_expiry_minutes)
    payload = {
        "sub": subject,
        "iat": issued_at,
        "exp": expires_at,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def validate_token(settings: Settings, token: str) -> AdminSession:
    """Validate `token` and return its claims.

    Raises `jwt.InvalidTokenError` (or a subclass, e.g. `ExpiredSignatureError`)
    for every failure mode: missing/invalid signature, expiry, wrong
    issuer/audience, or an algorithm outside the configured allowlist.
    Callers must catch `jwt.InvalidTokenError` and respond with one generic
    authentication error (Requirement 7.4) rather than branching on the
    specific exception type.
    """
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        options={"require": ["sub", "iat", "exp", "iss", "aud"]},
    )
    return AdminSession(
        subject=payload["sub"],
        issued_at=datetime.fromtimestamp(payload["iat"], tz=UTC),
        expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
    )
