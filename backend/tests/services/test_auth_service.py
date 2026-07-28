"""Unit tests for AuthService.login (Requirements 7.2, 7.9, 7.10, 10.11).

Uses a real Prisma-backed AdminUserRepository/AuditLogRepository (requires
DATABASE_URL; see tests/db/conftest.py) and the in-process FakeRedis double
for the login rate limiter, so no external Redis/Upstash service is needed.
"""

from __future__ import annotations

from app.core.jwt_auth import validate_token
from app.core.password_hashing import hash_password
from app.core.settings import Settings
from app.db.repositories import AdminUserRepository, AuditLogRepository
from app.redis.rate_limit import login_rate_limit_key
from app.services.auth_service import (
    LOGIN_RATE_LIMIT_MAX_ATTEMPTS,
    AuthService,
)
from prisma import Prisma

from tests.db.conftest import requires_database
from tests.redis.fakes import FakeRedis

_SETTINGS_KWARGS = {
    "DATABASE_URL": "postgresql://user:pass@localhost/db",
    "UPSTASH_REDIS_REST_URL": "https://example.upstash.io",
    "UPSTASH_REDIS_REST_TOKEN": "token",
    "R2_ENDPOINT": "https://account.r2.cloudflarestorage.com",
    "R2_ACCESS_KEY_ID": "key",
    "R2_SECRET_ACCESS_KEY": "secret",
    "R2_BUCKET": "bucket",
    "R2_PUBLIC_HOST": "https://images.example.com",
    "JWT_SECRET": "a-sufficiently-long-signing-secret-for-tests",
    "GEOIP_DATABASE_PATH": "/app/geoip/GeoLite2-Country.mmdb",
}


def _settings() -> Settings:
    return Settings(_env_file=None, **_SETTINGS_KWARGS)  # type: ignore[call-arg, arg-type]


async def _make_service(db: Prisma) -> AuthService:
    return AuthService(
        settings=_settings(),
        admin_users=AdminUserRepository(db),
        audit_log=AuditLogRepository(db),
        redis=FakeRedis(),  # type: ignore[arg-type]
    )


async def _seed_admin(db: Prisma, *, username: str, password: str) -> None:
    repo = AdminUserRepository(db)
    await repo.create({"username": username, "passwordHash": hash_password(password)})


@requires_database
class TestAuthServiceLogin:
    async def test_valid_credentials_return_a_usable_token(self, db: Prisma) -> None:
        await _seed_admin(db, username="admin-valid", password="correct-password")
        service = await _make_service(db)

        result = await service.login(
            username="admin-valid", password="correct-password", ip_address="203.0.113.1"
        )

        assert result.success is True
        assert result.token is not None
        session = validate_token(_settings(), result.token)
        assert session.subject == "admin-valid"

    async def test_invalid_password_returns_generic_error(self, db: Prisma) -> None:
        await _seed_admin(db, username="admin-badpw", password="correct-password")
        service = await _make_service(db)

        result = await service.login(
            username="admin-badpw", password="wrong-password", ip_address="203.0.113.2"
        )

        assert result.success is False
        assert result.token is None
        assert result.error is not None

    async def test_unknown_username_returns_the_same_generic_error_as_bad_password(
        self, db: Prisma
    ) -> None:
        await _seed_admin(db, username="admin-known", password="correct-password")
        service = await _make_service(db)

        unknown_result = await service.login(
            username="does-not-exist", password="anything", ip_address="203.0.113.3"
        )
        bad_password_result = await service.login(
            username="admin-known", password="wrong-password", ip_address="203.0.113.4"
        )

        assert unknown_result.error == bad_password_result.error

    async def test_exceeding_the_login_rate_limit_rejects_further_attempts(
        self, db: Prisma
    ) -> None:
        await _seed_admin(db, username="admin-ratelimit", password="correct-password")
        service = await _make_service(db)
        # Re-use the same service instance so all attempts share one FakeRedis.
        for _ in range(LOGIN_RATE_LIMIT_MAX_ATTEMPTS):
            await service.login(
                username="admin-ratelimit", password="wrong-password", ip_address="203.0.113.5"
            )

        limited_result = await service.login(
            username="admin-ratelimit", password="correct-password", ip_address="203.0.113.5"
        )

        assert limited_result.success is False
        assert limited_result.rate_limited is True

    async def test_rate_limit_recovers_once_the_window_elapses(self, db: Prisma) -> None:
        await _seed_admin(db, username="admin-recovers", password="correct-password")
        redis = FakeRedis()
        service = AuthService(
            settings=_settings(),
            admin_users=AdminUserRepository(db),
            audit_log=AuditLogRepository(db),
            redis=redis,  # type: ignore[arg-type]
        )
        for _ in range(LOGIN_RATE_LIMIT_MAX_ATTEMPTS):
            await service.login(
                username="admin-recovers", password="wrong-password", ip_address="203.0.113.6"
            )
        redis.force_expire_now(login_rate_limit_key("admin-recovers:203.0.113.6"))

        recovered_result = await service.login(
            username="admin-recovers", password="correct-password", ip_address="203.0.113.6"
        )

        assert recovered_result.success is True

    async def test_successful_login_is_audited_without_leaking_the_password(
        self, db: Prisma
    ) -> None:
        await _seed_admin(db, username="admin-audit-success", password="correct-password")
        service = await _make_service(db)

        await service.login(
            username="admin-audit-success",
            password="correct-password",
            ip_address="203.0.113.7",
        )

        entries = await AuditLogRepository(db).list_recent(limit=10)
        matching = [e for e in entries if e.actor == "admin-audit-success"]
        assert any(e.action == "login.success" and e.result == "success" for e in matching)
        assert all("correct-password" not in (e.action + e.result) for e in matching)

    async def test_failed_login_is_audited_without_leaking_the_password(self, db: Prisma) -> None:
        await _seed_admin(db, username="admin-audit-failure", password="correct-password")
        service = await _make_service(db)

        await service.login(
            username="admin-audit-failure", password="wrong-password", ip_address="203.0.113.8"
        )

        entries = await AuditLogRepository(db).list_recent(limit=10)
        matching = [e for e in entries if e.actor == "admin-audit-failure"]
        assert any(e.action == "login.failure" for e in matching)
        assert all("wrong-password" not in (e.action + e.result) for e in matching)
