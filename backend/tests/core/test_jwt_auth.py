"""Unit tests for JWT issuance/validation (Requirements 7.1, 7.3, 7.4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from app.core.jwt_auth import issue_token, validate_token
from app.core.settings import Settings

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


def _settings(**overrides: object) -> Settings:
    kwargs = dict(_SETTINGS_KWARGS)
    kwargs.update(overrides)
    return Settings(_env_file=None, **kwargs)  # type: ignore[call-arg, arg-type]


class TestIssueToken:
    def test_issued_token_contains_expected_claims(self) -> None:
        settings = _settings()

        token = issue_token(settings, subject="admin-1")
        decoded = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
        )

        assert decoded["sub"] == "admin-1"
        assert decoded["iss"] == settings.jwt_issuer
        assert decoded["aud"] == settings.jwt_audience
        assert "iat" in decoded
        assert "exp" in decoded


class TestValidateToken:
    def test_valid_unexpired_token_authorizes(self) -> None:
        settings = _settings()
        token = issue_token(settings, subject="admin-1")

        session = validate_token(settings, token)

        assert session.subject == "admin-1"

    def test_expired_token_is_rejected(self) -> None:
        settings = _settings()
        issued_at = datetime.now(UTC) - timedelta(hours=2)
        token = issue_token(settings, subject="admin-1", now=issued_at)

        with pytest.raises(jwt.ExpiredSignatureError):
            validate_token(settings, token)

    def test_tampered_signature_is_rejected(self) -> None:
        settings = _settings()
        token = issue_token(settings, subject="admin-1")
        tampered = token[:-4] + "abcd"

        with pytest.raises(jwt.InvalidTokenError):
            validate_token(settings, tampered)

    def test_token_signed_with_a_different_secret_is_rejected(self) -> None:
        settings = _settings()
        other_settings = _settings(JWT_SECRET="a-completely-different-signing-secret")
        token = issue_token(other_settings, subject="admin-1")

        with pytest.raises(jwt.InvalidTokenError):
            validate_token(settings, token)

    def test_alg_none_token_is_rejected(self) -> None:
        settings = _settings()
        forged_payload = {
            "sub": "admin-1",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        }
        forged_token = jwt.encode(forged_payload, key=None, algorithm="none")

        with pytest.raises(jwt.InvalidTokenError):
            validate_token(settings, forged_token)

    def test_unsupported_algorithm_is_rejected(self) -> None:
        settings = _settings()
        # Signed with a different algorithm than the one configured/allowlisted.
        forged_payload = {
            "sub": "admin-1",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        }
        forged_token = jwt.encode(forged_payload, settings.jwt_secret, algorithm="HS384")

        with pytest.raises(jwt.InvalidTokenError):
            validate_token(settings, forged_token)

    def test_wrong_issuer_is_rejected(self) -> None:
        settings = _settings()
        forged_payload = {
            "sub": "admin-1",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "iss": "someone-else",
            "aud": settings.jwt_audience,
        }
        forged_token = jwt.encode(forged_payload, settings.jwt_secret, algorithm="HS256")

        with pytest.raises(jwt.InvalidTokenError):
            validate_token(settings, forged_token)

    def test_wrong_audience_is_rejected(self) -> None:
        settings = _settings()
        forged_payload = {
            "sub": "admin-1",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "iss": settings.jwt_issuer,
            "aud": "someone-else",
        }
        forged_token = jwt.encode(forged_payload, settings.jwt_secret, algorithm="HS256")

        with pytest.raises(jwt.InvalidTokenError):
            validate_token(settings, forged_token)

    def test_missing_required_claim_is_rejected(self) -> None:
        settings = _settings()
        forged_payload = {
            "sub": "admin-1",
            "iat": datetime.now(UTC),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            # "exp" intentionally omitted
        }
        forged_token = jwt.encode(forged_payload, settings.jwt_secret, algorithm="HS256")

        with pytest.raises(jwt.InvalidTokenError):
            validate_token(settings, forged_token)

    def test_all_rejection_modes_raise_the_same_base_exception_type(self) -> None:
        # Requirement 7.4: callers respond with one generic error regardless
        # of failure mode, so every rejection must be catchable via the same
        # base `InvalidTokenError` type.
        settings = _settings()
        expired_token = issue_token(
            settings, subject="admin-1", now=datetime.now(UTC) - timedelta(hours=2)
        )
        tampered_token = issue_token(settings, subject="admin-1")[:-4] + "abcd"

        for bad_token in (expired_token, tampered_token, "not-a-jwt-at-all"):
            with pytest.raises(jwt.InvalidTokenError):
                validate_token(settings, bad_token)
