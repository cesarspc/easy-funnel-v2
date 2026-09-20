"""Environment-based infrastructure and bootstrap settings.

Deployment concerns come from environment variables. Merchant-facing values
are seeded from ``STORE_*`` only on a fresh database, then live in the admin-
editable singleton store record. Generic Redis and S3 settings make the same
application work with the bundled services or compatible external providers.

`get_settings()` is cached so the environment is parsed once per process;
tests that need different values construct `Settings(...)` directly instead
of mutating process environment variables.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Neon PostgreSQL (via Prisma) ---
    database_url: str = Field(alias="DATABASE_URL")

    # --- Redis (standard wire protocol; works with self-hosted Redis) ---
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # --- Cloudflare R2 ---
    r2_endpoint: str | None = Field(default=None, alias="R2_ENDPOINT")
    r2_access_key_id: str | None = Field(default=None, alias="R2_ACCESS_KEY_ID")
    r2_secret_access_key: str | None = Field(default=None, alias="R2_SECRET_ACCESS_KEY")
    r2_bucket: str | None = Field(default=None, alias="R2_BUCKET")
    r2_public_host: str | None = Field(default=None, alias="R2_PUBLIC_HOST")

    # Vendor-neutral S3 aliases. Existing R2 names remain accepted so an
    # operator can upgrade without rotating storage credentials.
    s3_endpoint: str | None = Field(default=None, alias="S3_ENDPOINT")
    s3_region: str = Field(default="us-east-1", alias="S3_REGION")
    s3_access_key_id: str | None = Field(default=None, alias="S3_ACCESS_KEY_ID")
    s3_secret_access_key: str | None = Field(default=None, alias="S3_SECRET_ACCESS_KEY")
    s3_bucket: str | None = Field(default=None, alias="S3_BUCKET")
    s3_public_base_url: str | None = Field(default=None, alias="S3_PUBLIC_BASE_URL")

    # --- JWT / Administrator sessions ---
    jwt_secret: str = Field(alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expiry_minutes: int = Field(default=60, alias="JWT_EXPIRY_MINUTES")
    jwt_issuer: str = Field(default="cod-commerce-platform", alias="JWT_ISSUER")
    jwt_audience: str = Field(default="cod-commerce-admin", alias="JWT_AUDIENCE")

    # --- GeoIP (self-hosted GeoLite2) ---
    geoip_database_path: str = Field(alias="GEOIP_DATABASE_PATH")
    geoip_update_url: str | None = Field(default=None, alias="GEOIP_UPDATE_URL")

    # --- MasterShop fulfillment ---
    # Optional for rolling-deploy safety: a missing secret never prevents the
    # API from booting or accepting local orders. The durable sync row records
    # the configuration failure until the secret is configured and retried.
    mastershop_api_key: str | None = Field(default=None, alias="MASTERSHOP_API_KEY")
    mastershop_orders_url: str = Field(
        default="https://prod.api.mastershop.com/api/orders",
        alias="MASTERSHOP_ORDERS_URL",
    )
    mastershop_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        le=30,
        alias="MASTERSHOP_TIMEOUT_SECONDS",
    )
    fulfillment_provider: Literal["none", "mastershop"] = Field(
        default="none", alias="FULFILLMENT_PROVIDER"
    )

    # --- Store bootstrap (applied only while store_settings is absent) ---
    store_name: str = Field(default="Mi Tienda", alias="STORE_NAME")
    store_legal_name: str = Field(default="", alias="STORE_LEGAL_NAME")
    store_primary_color: str = Field(default="#30503b", alias="STORE_PRIMARY_COLOR")
    store_whatsapp_number: str = Field(default="", alias="STORE_WHATSAPP_NUMBER")
    store_whatsapp_message: str = Field(
        default="Hola, me gustaría conocer más sobre tus productos.",
        alias="STORE_WHATSAPP_MESSAGE",
    )
    store_support_email: str = Field(default="", alias="STORE_SUPPORT_EMAIL")

    # --- Admin bootstrap ---
    # When both are set, startup provisions this Administrator if it is missing.
    # An existing account is left untouched unless `admin_password_reset` is on,
    # so a restart never silently reverts a rotated password.
    admin_username: str | None = Field(default=None, alias="ADMIN_USERNAME")
    admin_password: str | None = Field(default=None, alias="ADMIN_PASSWORD")
    admin_password_reset: bool = Field(default=False, alias="ADMIN_PASSWORD_RESET")

    # --- CORS ---
    cors_allowed_origins: str = Field(
        default="http://localhost:5173",
        alias="CORS_ALLOWED_ORIGINS",
    )

    # --- Deployment ---
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    environment: str = Field(default="development", alias="ENVIRONMENT")

    @property
    def storage_endpoint(self) -> str:
        return self.s3_endpoint or self.r2_endpoint or ""

    @property
    def storage_access_key_id(self) -> str:
        return self.s3_access_key_id or self.r2_access_key_id or ""

    @property
    def storage_secret_access_key(self) -> str:
        return self.s3_secret_access_key or self.r2_secret_access_key or ""

    @property
    def storage_bucket(self) -> str:
        return self.s3_bucket or self.r2_bucket or ""

    @property
    def storage_public_base_url(self) -> str:
        return self.s3_public_base_url or self.r2_public_host or ""


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide `Settings` instance, parsing the env once."""
    return Settings()  # type: ignore[call-arg]
