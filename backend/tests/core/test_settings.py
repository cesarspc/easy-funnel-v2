"""Unit tests for environment-based settings parsing (Requirement 9.3).

These tests assert on `Settings` parsing in isolation: what the explicitly
passed values produce and what the documented defaults are. Pydantic settings
always consults `os.environ`, and the test session populates it with a working
test configuration (see `tests/conftest.py`), so every test here first clears
the process environment of the variables `Settings` reads. Without that, an
ambient `ENVIRONMENT=test` or `JWT_SECRET` would silently change the result
and the suite's outcome would depend on the machine it runs on.
"""

from __future__ import annotations

import pytest
from app.core.settings import Settings
from pydantic import ValidationError


@pytest.fixture(autouse=True)
def _environment_isolated_from_the_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every variable `Settings` reads from the process environment.

    Derived from the model itself so new settings fields are covered
    automatically.
    """
    for field in Settings.model_fields.values():
        if field.alias:
            monkeypatch.delenv(field.alias, raising=False)


_REQUIRED_ENV = {
    "DATABASE_URL": "postgresql://user:pass@localhost/db",
    "UPSTASH_REDIS_REST_URL": "https://example.upstash.io",
    "UPSTASH_REDIS_REST_TOKEN": "token",
    "R2_ENDPOINT": "https://account.r2.cloudflarestorage.com",
    "R2_ACCESS_KEY_ID": "key",
    "R2_SECRET_ACCESS_KEY": "secret",
    "R2_BUCKET": "bucket",
    "R2_PUBLIC_HOST": "https://images.example.com",
    "JWT_SECRET": "signing-secret",
    "GEOIP_DATABASE_PATH": "/app/geoip/GeoLite2-Country.mmdb",
}


class TestSettingsParsing:
    def test_parses_all_required_variables(self) -> None:
        settings = Settings(_env_file=None, **_REQUIRED_ENV)  # type: ignore[call-arg]

        assert settings.database_url == _REQUIRED_ENV["DATABASE_URL"]
        assert settings.upstash_redis_rest_url == _REQUIRED_ENV["UPSTASH_REDIS_REST_URL"]
        assert settings.r2_bucket == _REQUIRED_ENV["R2_BUCKET"]
        assert settings.jwt_secret == _REQUIRED_ENV["JWT_SECRET"]
        assert settings.geoip_database_path == _REQUIRED_ENV["GEOIP_DATABASE_PATH"]

    def test_optional_fields_have_documented_defaults(self) -> None:
        settings = Settings(_env_file=None, **_REQUIRED_ENV)  # type: ignore[call-arg]

        assert settings.jwt_algorithm == "HS256"
        assert settings.jwt_expiry_minutes == 60
        assert settings.jwt_issuer == "cod-commerce-platform"
        assert settings.jwt_audience == "cod-commerce-admin"
        assert settings.app_version == "0.1.0"
        assert settings.environment == "development"
        assert settings.geoip_update_url is None

    def test_missing_required_variable_raises(self) -> None:
        incomplete = dict(_REQUIRED_ENV)
        del incomplete["JWT_SECRET"]

        with pytest.raises(ValidationError):
            Settings(_env_file=None, **incomplete)  # type: ignore[call-arg]

    def test_deployment_values_are_overridable(self) -> None:
        overrides = dict(_REQUIRED_ENV)
        overrides["APP_VERSION"] = "1.2.3"
        overrides["ENVIRONMENT"] = "production"

        settings = Settings(_env_file=None, **overrides)  # type: ignore[call-arg]

        assert settings.app_version == "1.2.3"
        assert settings.environment == "production"
