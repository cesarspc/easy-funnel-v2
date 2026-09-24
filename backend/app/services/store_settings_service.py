"""Single-merchant settings, bootstrap, validation, and brand assets."""

from __future__ import annotations

import contextlib
import re
import uuid
from typing import Any

from prisma import Prisma

from app.core.regional import (
    RegionalValidationError,
    validate_country_code,
    validate_currency,
    validate_locale,
    validate_phone_country_code,
    validate_phone_national_pattern,
    validate_time_zone,
)
from app.core.settings import Settings
from app.domains.images.validation import validate_source_image
from app.services.platform_config import FULFILLMENT_PROVIDERS, invalidate_platform_config
from app.storage.r2_client import R2Client, object_public_url

_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_PHONE = re.compile(r"^\+[1-9][0-9]{6,14}$")
_GTM = re.compile(r"^(|GTM-[A-Z0-9]+)$")
_PIXEL = re.compile(r"^(|[0-9]{5,30})$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_HTTP_URL = re.compile(r"^https?://[^\s/$.?#][^\s]*$", re.IGNORECASE)
_REGIONAL_VALIDATORS = {
    "countryCode": validate_country_code,
    "locale": validate_locale,
    "currency": validate_currency,
    "timeZone": validate_time_zone,
    "phoneCountryCode": validate_phone_country_code,
    "phoneNationalPattern": validate_phone_national_pattern,
}
_ASSET_KINDS = {"logo", "favicon", "homepage_image"}
_EXTENSIONS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
_CONTENT_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


class StoreSettingsValidationError(ValueError):
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(message)


def _clean(value: Any, field: str, maximum: int, *, required: bool = False) -> str:
    if not isinstance(value, str):
        raise StoreSettingsValidationError(field, "Must be text.")
    value = value.strip()
    if required and not value:
        raise StoreSettingsValidationError(field, "This field is required.")
    if len(value) > maximum:
        raise StoreSettingsValidationError(field, f"Must be at most {maximum} characters.")
    return value


def validate_store_update(values: dict[str, Any]) -> dict[str, Any]:
    limits = {
        "storeName": (100, True), "legalName": (160, False),
        "whatsappMessage": (500, False),
        "homeEyebrow": (100, False), "homeHeadline": (180, True),
        "homeDescription": (500, False), "homeCtaLabel": (80, True),
        "secondaryHeadline": (180, False), "secondaryDescription": (500, False),
        "footerText": (240, False), "seoTitle": (70, True),
        "seoDescription": (180, False),
    }
    cleaned: dict[str, Any] = {}
    for field, value in values.items():
        if field in limits:
            maximum, required = limits[field]
            cleaned[field] = _clean(value, field, maximum, required=required)
        elif field == "primaryColor":
            color = _clean(value, field, 7, required=True).lower()
            if not _COLOR.fullmatch(color):
                raise StoreSettingsValidationError(field, "Use a six-digit hexadecimal color.")
            cleaned[field] = color
        elif field == "whatsappNumber":
            phone = _clean(value, field, 16)
            if phone and not _PHONE.fullmatch(phone):
                raise StoreSettingsValidationError(
                    field, "Use international format: + followed by the country code and number."
                )
            cleaned[field] = phone
        elif field == "supportEmail":
            email = _clean(value, field, 254).lower()
            if email and not _EMAIL.fullmatch(email):
                raise StoreSettingsValidationError(field, "Use a valid email address.")
            cleaned[field] = email
        elif field == "gtmContainerId":
            code = _clean(value, field, 20).upper()
            if not _GTM.fullmatch(code):
                raise StoreSettingsValidationError(field, "Use a valid GTM container ID.")
            cleaned[field] = code
        elif field == "metaPixelId":
            code = _clean(value, field, 30)
            if not _PIXEL.fullmatch(code):
                raise StoreSettingsValidationError(field, "Use a numeric Meta Pixel ID.")
            cleaned[field] = code
        elif field == "trustItems":
            if not isinstance(value, list) or len(value) > 3:
                raise StoreSettingsValidationError(field, "Provide at most three trust items.")
            cleaned[field] = [_clean(item, field, 80, required=True) for item in value]
        elif field in _REGIONAL_VALIDATORS:
            try:
                cleaned[field] = _REGIONAL_VALIDATORS[field](_clean(value, field, 100))
            except RegionalValidationError as exc:
                raise StoreSettingsValidationError(exc.field, exc.message) from exc
        elif field == "fulfillmentProvider":
            provider = _clean(value, field, 20, required=True).lower()
            if provider not in FULFILLMENT_PROVIDERS:
                raise StoreSettingsValidationError(
                    field, f"Use one of: {', '.join(sorted(FULFILLMENT_PROVIDERS))}."
                )
            cleaned[field] = provider
        elif field == "mastershopOrdersUrl":
            url = _clean(value, field, 2048)
            if url and not _HTTP_URL.fullmatch(url):
                raise StoreSettingsValidationError(field, "Use a valid http(s) URL.")
            cleaned[field] = url
        elif field == "mastershopTimeoutSeconds":
            if isinstance(value, bool) or not isinstance(value, int | float) or not 0 < value <= 30:
                raise StoreSettingsValidationError(
                    field, "Use a number of seconds between 0 and 30."
                )
            cleaned[field] = float(value)
        elif field == "mastershopApiKey":
            # Write-only secret: never echoed back by the API.
            cleaned[field] = _clean(value, field, 512)
    return cleaned


def _fulfillment_bootstrap(settings: Settings) -> dict[str, Any]:
    return validate_store_update({
        "fulfillmentProvider": settings.fulfillment_provider,
        "mastershopOrdersUrl": settings.mastershop_orders_url,
        "mastershopTimeoutSeconds": settings.mastershop_timeout_seconds,
        "mastershopApiKey": settings.mastershop_api_key or "",
    })


async def ensure_store_settings(db: Prisma, settings: Settings) -> None:
    """Create the singleton from bootstrap variables, or fill never-set fields.

    Environment values are applied exactly once; afterwards the database row
    is authoritative and a restart never reverts an Admin edit.
    """
    existing = await db.storesettings.find_unique(where={"id": 1})
    if existing is not None:
        if existing.fulfillmentProvider is None:
            await db.storesettings.update(where={"id": 1}, data=_fulfillment_bootstrap(settings))
            invalidate_platform_config()
        return
    data = validate_store_update({
        "storeName": settings.store_name,
        "legalName": settings.store_legal_name,
        "primaryColor": settings.store_primary_color,
        "whatsappNumber": settings.store_whatsapp_number,
        "whatsappMessage": settings.store_whatsapp_message,
        "supportEmail": settings.store_support_email,
        "seoTitle": settings.store_name,
        "countryCode": settings.store_country_code,
        "locale": settings.store_locale,
        "currency": settings.store_currency,
        "timeZone": settings.store_time_zone,
        "phoneCountryCode": settings.store_phone_country_code,
        "phoneNationalPattern": settings.store_phone_national_pattern,
    })
    await db.storesettings.create(data={"id": 1, **data, **_fulfillment_bootstrap(settings)})
    invalidate_platform_config()


class StoreSettingsService:
    def __init__(self, db: Prisma):
        self._db = db

    async def get(self):  # type: ignore[no-untyped-def]
        return await self._db.storesettings.find_unique(where={"id": 1})

    async def update(self, values: dict[str, Any], *, actor: str):  # type: ignore[no-untyped-def]
        cleaned = validate_store_update(values)
        async with self._db.tx() as tx:
            store = await tx.storesettings.update(where={"id": 1}, data=cleaned)
            await tx.auditlog.create(data={"actor": actor, "action": "store.settings.updated", "targetType": "store_settings", "targetId": "1", "result": "success"})
        invalidate_platform_config()
        return store

    async def upload_asset(self, kind: str, raw: bytes, storage: R2Client, public_base: str, *, actor: str):  # type: ignore[no-untyped-def]
        if kind not in _ASSET_KINDS:
            raise StoreSettingsValidationError("asset_kind", "Unsupported brand asset.")
        image = validate_source_image(raw)
        ext = _EXTENSIONS[image.format]
        key = f"brand/{kind}/{uuid.uuid4().hex}.{ext}"
        await storage.put_bytes(key, raw, content_type=_CONTENT_TYPES[ext])
        current = await self.get()
        key_field = {"logo": "logoObjectKey", "favicon": "faviconObjectKey", "homepage_image": "homepageImageObjectKey"}[kind]
        url_field = {"logo": "logoUrl", "favicon": "faviconUrl", "homepage_image": "homepageImageUrl"}[kind]
        previous = getattr(current, key_field) if current else None
        try:
            stored = await self._db.storesettings.update(where={"id": 1}, data={key_field: key, url_field: object_public_url(public_base, key)})
            await self._db.auditlog.create(data={"actor": actor, "action": "store.asset.uploaded", "targetType": kind, "targetId": "1", "result": "success"})
        except Exception:
            with contextlib.suppress(Exception):
                await storage.delete(key)
            raise
        if previous:
            with contextlib.suppress(Exception):
                await storage.delete(previous)
        return stored
