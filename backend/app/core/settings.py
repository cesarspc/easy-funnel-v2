"""Environment-based application settings.

Single source of truth for configuration (Requirement 9.3): Neon PostgreSQL,
Upstash Redis, Cloudflare R2, JWT signing, GeoIP, and deployment values all
come from environment variables — never hard-coded, never committed. See
`.env.example` for the documented variable names and safe placeholder
examples.

`get_settings()` is cached so the environment is parsed once per process;
tests that need different values construct `Settings(...)` directly instead
of mutating process environment variables.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Neon PostgreSQL (via Prisma) ---
    database_url: str = Field(alias="DATABASE_URL")

    # --- Upstash Redis ---
    upstash_redis_rest_url: str = Field(alias="UPSTASH_REDIS_REST_URL")
    upstash_redis_rest_token: str = Field(alias="UPSTASH_REDIS_REST_TOKEN")

    # --- Cloudflare R2 ---
    r2_endpoint: str = Field(alias="R2_ENDPOINT")
    r2_access_key_id: str = Field(alias="R2_ACCESS_KEY_ID")
    r2_secret_access_key: str = Field(alias="R2_SECRET_ACCESS_KEY")
    r2_bucket: str = Field(alias="R2_BUCKET")
    r2_public_host: str = Field(alias="R2_PUBLIC_HOST")

    # --- JWT / Administrator sessions ---
    jwt_secret: str = Field(alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expiry_minutes: int = Field(default=60, alias="JWT_EXPIRY_MINUTES")
    jwt_issuer: str = Field(default="cod-commerce-platform", alias="JWT_ISSUER")
    jwt_audience: str = Field(default="cod-commerce-admin", alias="JWT_AUDIENCE")

    # --- GeoIP (self-hosted GeoLite2) ---
    geoip_database_path: str = Field(alias="GEOIP_DATABASE_PATH")
    geoip_update_url: str | None = Field(default=None, alias="GEOIP_UPDATE_URL")

    # --- Deployment ---
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    environment: str = Field(default="development", alias="ENVIRONMENT")


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide `Settings` instance, parsing the env once."""
    return Settings()  # type: ignore[call-arg]
