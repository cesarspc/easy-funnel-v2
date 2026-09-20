"""Public and authenticated single-store configuration endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.core.auth_dependencies import require_admin
from app.core.settings import Settings, get_settings
from app.db.client import get_prisma
from app.domains.images.errors import ImageValidationError
from app.services.store_settings_service import StoreSettingsService, StoreSettingsValidationError
from app.storage.dependencies import get_r2_client
from app.storage.r2_client import R2Client

public_router = APIRouter(prefix="/api/public/store", tags=["public", "store"])
admin_router = APIRouter(prefix="/api/admin/store", tags=["admin", "store"])


class StoreResponse(BaseModel):
    store_name: str
    legal_name: str
    primary_color: str
    logo_url: str | None
    favicon_url: str | None
    homepage_image_url: str | None
    whatsapp_number: str
    whatsapp_message: str
    support_email: str
    home_eyebrow: str
    home_headline: str
    home_description: str
    home_cta_label: str
    trust_items: list[str]
    secondary_headline: str
    secondary_description: str
    footer_text: str
    seo_title: str
    seo_description: str
    gtm_container_id: str
    meta_pixel_id: str


class StoreUpdateRequest(BaseModel):
    store_name: str | None = None
    legal_name: str | None = None
    primary_color: str | None = None
    whatsapp_number: str | None = None
    whatsapp_message: str | None = None
    support_email: str | None = None
    home_eyebrow: str | None = None
    home_headline: str | None = None
    home_description: str | None = None
    home_cta_label: str | None = None
    trust_items: list[str] | None = Field(default=None, max_length=3)
    secondary_headline: str | None = None
    secondary_description: str | None = None
    footer_text: str | None = None
    seo_title: str | None = None
    seo_description: str | None = None
    gtm_container_id: str | None = None
    meta_pixel_id: str | None = None


_FIELDS = {
    "store_name": "storeName", "legal_name": "legalName", "primary_color": "primaryColor",
    "whatsapp_number": "whatsappNumber", "whatsapp_message": "whatsappMessage",
    "support_email": "supportEmail", "home_eyebrow": "homeEyebrow",
    "home_headline": "homeHeadline", "home_description": "homeDescription",
    "home_cta_label": "homeCtaLabel", "trust_items": "trustItems",
    "secondary_headline": "secondaryHeadline", "secondary_description": "secondaryDescription",
    "footer_text": "footerText", "seo_title": "seoTitle", "seo_description": "seoDescription",
    "gtm_container_id": "gtmContainerId", "meta_pixel_id": "metaPixelId",
}


def serialize(store: Any) -> StoreResponse:
    return StoreResponse(**{snake: (list(getattr(store, camel) or []) if snake == "trust_items" else getattr(store, camel)) for snake, camel in _FIELDS.items()}, logo_url=store.logoUrl, favicon_url=store.faviconUrl, homepage_image_url=store.homepageImageUrl)


def validation_error(exc: Exception) -> HTTPException:
    if isinstance(exc, StoreSettingsValidationError):
        detail = {"field": exc.field, "message": exc.message}
    elif isinstance(exc, ImageValidationError):
        detail = {"field": "file", "message": str(exc)}
    else:
        detail = "Invalid store settings."
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


@public_router.get("", response_model=StoreResponse, summary="Read storefront settings")
async def public_store() -> StoreResponse:
    """Return the merchant's public storefront configuration.

    Branding, contact details, homepage copy, SEO fields and tracking
    identifiers — everything a storefront needs to render itself. Unauthenticated
    and safe to call from a buyer's browser; it carries no operational data.

    Answers `503` while the singleton has not been initialised, which happens
    only before the service has completed its first start-up against an empty
    database.
    """
    store = await StoreSettingsService(get_prisma()).get()
    if store is None:
        raise HTTPException(503, "Store is not configured.")
    return serialize(store)


@admin_router.get("", response_model=StoreResponse, summary="Read storefront settings (admin)")
async def admin_store(admin=Depends(require_admin)) -> StoreResponse:  # type: ignore[no-untyped-def] # noqa: B008
    """Return the same storefront configuration the public endpoint serves.

    Separate from the public route so the editing surface reads through an
    authenticated path and its access is audited like every other admin read.
    """
    del admin
    store = await StoreSettingsService(get_prisma()).get()
    if store is None:
        raise HTTPException(503, "Store is not configured.")
    return serialize(store)


@admin_router.patch("", response_model=StoreResponse, summary="Update storefront settings")
async def update_store(request: StoreUpdateRequest, admin=Depends(require_admin)) -> StoreResponse:  # type: ignore[no-untyped-def] # noqa: B008
    """Update storefront settings and return the stored result.

    A partial update: only the fields present in the body are written, so a
    client can send one field without restating the rest. Values are validated
    (colors, WhatsApp number format, e-mail, tracking identifiers, lengths) and a
    rejection names the offending field.

    These values seed from `STORE_*` environment variables **once**, on a fresh
    database. After that this endpoint is the source of truth and a restart never
    reverts what the merchant saved here.
    """
    values = {_FIELDS[key]: value for key, value in request.model_dump(exclude_unset=True).items()}
    try:
        return serialize(await StoreSettingsService(get_prisma()).update(values, actor=admin.subject))
    except StoreSettingsValidationError as exc:
        raise validation_error(exc) from exc


@admin_router.post(
    "/assets/{asset_kind}",
    response_model=StoreResponse,
    summary="Upload a brand image",
)
async def upload_store_asset(asset_kind: str, file: UploadFile = File(...), admin=Depends(require_admin), storage: R2Client = Depends(get_r2_client), settings: Settings = Depends(get_settings)) -> StoreResponse:  # type: ignore[no-untyped-def] # noqa: B008
    """Replace one brand image and return the updated settings.

    `asset_kind` is one of `logo`, `favicon` or `homepage_image`. The upload is
    validated as an image, stored under a random opaque key, and the settings
    record is pointed at the new public URL. Send it as `multipart/form-data`
    with the image in a `file` part.
    """
    try:
        store = await StoreSettingsService(get_prisma()).upload_asset(asset_kind, await file.read(), storage, settings.storage_public_base_url, actor=admin.subject)
        return serialize(store)
    except (StoreSettingsValidationError, ImageValidationError) as exc:
        raise validation_error(exc) from exc
