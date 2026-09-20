"""Single-merchant settings, bootstrap, validation, and brand assets."""

from __future__ import annotations

import contextlib
import re
import uuid
from typing import Any

from prisma import Prisma

from app.core.settings import Settings
from app.domains.images.validation import validate_source_image
from app.storage.r2_client import R2Client, object_public_url

_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_PHONE = re.compile(r"^\+57[0-9]{10}$")
_GTM = re.compile(r"^(|GTM-[A-Z0-9]+)$")
_PIXEL = re.compile(r"^(|[0-9]{5,30})$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
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
                raise StoreSettingsValidationError(field, "Use +57 followed by 10 digits.")
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
    return cleaned


async def ensure_store_settings(db: Prisma, settings: Settings) -> None:
    if await db.storesettings.find_unique(where={"id": 1}) is not None:
        return
    data = validate_store_update({
        "storeName": settings.store_name,
        "legalName": settings.store_legal_name,
        "primaryColor": settings.store_primary_color,
        "whatsappNumber": settings.store_whatsapp_number,
        "whatsappMessage": settings.store_whatsapp_message,
        "supportEmail": settings.store_support_email,
        "seoTitle": settings.store_name,
    })
    await db.storesettings.create(data={"id": 1, **data})


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
