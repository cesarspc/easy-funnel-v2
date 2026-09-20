"""Administrator login orchestration: rate limiting, credential check, audit.

Composes the auth core (password hashing + JWT), the Upstash Redis rolling-
window login rate limiter (Requirement 7.9), and the audit log (Requirement
7.10) into the single `AuthService.login` use case. Kept in `services/`
rather than `core/` because it depends on repositories (`db`) and the Redis
rate limiter, not just pure auth primitives.
"""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis as AsyncRedis

from app.core.jwt_auth import issue_token
from app.core.password_hashing import verify_password
from app.core.settings import Settings
from app.db.repositories import AdminUserRepository, AuditLogRepository
from app.redis.rate_limit import check_rate_limit, login_rate_limit_key

# Login-specific rolling-window defaults (Requirement 7.9). Unlike the fraud
# rate limits, these are not currently Administrator-configurable, so they
# are module-level constants rather than a `fraud_config`-style DB row.
LOGIN_RATE_LIMIT_MAX_ATTEMPTS = 5
LOGIN_RATE_LIMIT_WINDOW_SECONDS = 600  # 10 minutes

_GENERIC_LOGIN_ERROR = "Invalid username or password."
_RATE_LIMITED_ERROR = "Too many login attempts. Try again later."


@dataclass(frozen=True)
class LoginResult:
    """Outcome of a login attempt: exactly one of `token` or `error` is set."""

    token: str | None
    error: str | None
    rate_limited: bool = False

    @property
    def success(self) -> bool:
        return self.token is not None


class AuthService:
    def __init__(
        self,
        *,
        settings: Settings,
        admin_users: AdminUserRepository,
        audit_log: AuditLogRepository,
        redis: AsyncRedis,
    ) -> None:
        self._settings = settings
        self._admin_users = admin_users
        self._audit_log = audit_log
        self._redis = redis

    async def login(self, *, username: str, password: str, ip_address: str) -> LoginResult:
        """Authenticate an Administrator login attempt.

        Order of operations: rate-limit check first (so a locked-out
        identifier never reaches password verification), then credential
        check, then audit. Every failure path returns the same generic
        error message (Requirement 7.2) regardless of which check failed —
        callers must not branch UI copy on `LoginResult.error` content vs.
        `rate_limited` beyond the 429 status code itself.
        """
        rate_limit_outcome = await check_rate_limit(
            self._redis,
            login_rate_limit_key(f"{username}:{ip_address}"),
            max_attempts=LOGIN_RATE_LIMIT_MAX_ATTEMPTS,
            window_seconds=LOGIN_RATE_LIMIT_WINDOW_SECONDS,
        )
        if rate_limit_outcome.triggered:
            await self._audit_log.record(
                actor=username, action="login.failure", result="rate_limited"
            )
            return LoginResult(token=None, error=_RATE_LIMITED_ERROR, rate_limited=True)

        admin_user = await self._admin_users.get_by_username(username)
        if admin_user is None or not verify_password(admin_user.passwordHash, password):
            await self._audit_log.record(
                actor=username, action="login.failure", result="invalid_credentials"
            )
            return LoginResult(token=None, error=_GENERIC_LOGIN_ERROR)

        token = issue_token(self._settings, subject=username)
        await self._audit_log.record(actor=username, action="login.success", result="success")
        return LoginResult(token=token, error=None)
