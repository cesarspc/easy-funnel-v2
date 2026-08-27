"""Admin endpoints for reusable Landing configuration templates.

Thin HTTP layer over `LandingTemplateService`. Saving snapshots one landing's
configuration and conversion components under a name; loading applies a saved
template to another landing and lives on the landings router instead
(`POST /api/admin/landings/{landing_id}/load-template`), because its response
is the updated landing detail the editor re-renders from.

This is a separate router rather than more paths under
`/api/admin/landings` so that a literal segment can never be shadowed by that
router's `/{landing_id}` parameter, which would answer `GET .../templates` with
a 422 about "templates" not being an integer.

Error mapping:

- `TemplateNotFoundError` -> `404`
- `LandingNotFoundError` -> `404`
- `LandingValidationError` -> `422` with `{"field", "message"}` (Requirement 8.19)
- `DuplicateTemplateNameError` -> `409`, so the dashboard can offer to
  overwrite the existing template instead of silently replacing it
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.auth_dependencies import require_admin
from app.core.settings import Settings, get_settings
from app.db.client import get_prisma
from app.domains.images.errors import (
    ImagePipelineUnavailableError,
    ImageValidationError,
    OpaqueKeyGenerationError,
)
from app.domains.landings.errors import (
    DuplicateSlugError,
    LandingNotFoundError,
    LandingValidationError,
)
from app.domains.products.errors import DuplicateSkuError, ProductValidationError
from app.domains.videos import VideoPipelineError, VideoValidationError
from app.services.landing_template_instantiation_service import (
    LandingTemplateInstantiationService,
    TemplateVersionConflictError,
)
from app.services.landing_template_service import (
    DuplicateTemplateNameError,
    LandingTemplateService,
    TemplateNotFoundError,
)
from app.storage.dependencies import get_r2_client
from app.storage.r2_client import R2Client

router = APIRouter(prefix="/api/admin/landing-templates", tags=["admin", "landing-templates"])


class LandingTemplateResponse(BaseModel):
    """One saved template.

    `banner_count` is the number of banners the source landing had and the
    number a target landing must have for this template to load — the dashboard
    shows it next to the name so the merchant can see which templates apply
    before opening anything.
    """

    id: int
    name: str
    banner_count: int
    block_count: int
    created_at: str
    updated_at: str


class LandingTemplateListResponse(BaseModel):
    templates: list[LandingTemplateResponse]


class LandingTemplateSaveRequest(BaseModel):
    landing_id: int
    name: str
    #: Replace an existing template of the same name. False (the default) makes
    #: a collision a 409 so the merchant is asked first.
    overwrite: bool = False


class TemplateProductCreateRequest(BaseModel):
    name: str
    sku: str
    price: Decimal
    description: str = ""
    variant_options: list[dict[str, Any]] = Field(default_factory=list)


class TemplateLandingCreateRequest(BaseModel):
    slug: str


class R2BannerSourceRequest(BaseModel):
    original_url: str
    alt_text: str


class R2VideoSourceRequest(BaseModel):
    original_url: str
    caption: str | None = None


class R2OfferImageSourceRequest(BaseModel):
    quantity: int = Field(strict=True, ge=1)
    original_url: str


class TemplateBlockAssetsRequest(BaseModel):
    block_index: int = Field(strict=True, ge=0)
    videos: list[R2VideoSourceRequest] = Field(default_factory=list)
    offer_images: list[R2OfferImageSourceRequest] = Field(default_factory=list)


class LandingTemplateInstantiateRequest(BaseModel):
    template_version: str
    product: TemplateProductCreateRequest
    landing: TemplateLandingCreateRequest
    banners: list[R2BannerSourceRequest]
    block_assets: list[TemplateBlockAssetsRequest] = Field(default_factory=list)


class LandingTemplateInstantiateResponse(BaseModel):
    product_id: int
    product_status: str
    landing_id: int
    landing_status: str
    slug: str
    public_path: str


class LandingTemplateCreationContractResponse(BaseModel):
    template_id: int
    template_name: str
    template_version: str
    banner_count: int
    media_blocks: list[dict[str, Any]]
    expected_payload: dict[str, Any]


def _field_error(field: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"field": field, "message": message},
    )


def _to_template_response(template) -> LandingTemplateResponse:  # type: ignore[no-untyped-def]
    blocks = template.blocks if isinstance(template.blocks, list) else []
    return LandingTemplateResponse(
        id=template.id,
        name=template.name,
        banner_count=template.bannerCount,
        block_count=len(blocks),
        created_at=template.createdAt.isoformat(),
        updated_at=template.updatedAt.isoformat(),
    )


def _expected_payload(contract: dict[str, Any], settings: Settings) -> dict[str, Any]:
    source_example = f"{settings.r2_public_host.rstrip('/')}/originals/<opaque-file-name>"
    block_assets: list[dict[str, Any]] = []
    for block in contract["media_blocks"]:
        if block["block_type"] == "video_carousel":
            block_assets.append(
                {
                    "block_index": block["block_index"],
                    "videos": [{"original_url": source_example, "caption": ""}],
                }
            )
        else:
            block_assets.append(
                {
                    "block_index": block["block_index"],
                    "offer_images": [
                        {"quantity": quantity, "original_url": source_example}
                        for quantity in block["offer_images"]["quantities"]
                    ],
                }
            )
    return {
        "template_version": contract["template_version"],
        "product": {
            "name": "",
            "sku": "",
            "price": 0,
            "description": "",
            "variant_options": [],
        },
        "landing": {"slug": ""},
        "banners": [
            {"original_url": source_example, "alt_text": ""}
            for _ in range(contract["banner_count"])
        ],
        "block_assets": block_assets,
    }


@router.get("", response_model=LandingTemplateListResponse)
async def list_landing_templates(
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> LandingTemplateListResponse:
    """Every saved template, most recently updated first."""
    service = LandingTemplateService(get_prisma())
    templates = await service.list_templates()
    return LandingTemplateListResponse(
        templates=[_to_template_response(template) for template in templates]
    )


@router.get(
    "/{template_id}/creation-contract",
    response_model=LandingTemplateCreationContractResponse,
)
async def get_landing_template_creation_contract(
    template_id: int,
    settings: Settings = Depends(get_settings),  # noqa: B008
    r2: R2Client = Depends(get_r2_client),  # noqa: B008
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008
) -> LandingTemplateCreationContractResponse:
    """Describe the exact product, banner and per-block media payload required."""
    service = LandingTemplateInstantiationService(
        get_prisma(), r2, public_host=settings.r2_public_host
    )
    try:
        contract = await service.creation_contract(template_id)
    except TemplateNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Landing template not found"
        ) from exc
    except LandingValidationError as exc:
        raise _field_error(exc.field, exc.message) from exc
    return LandingTemplateCreationContractResponse(
        **contract, expected_payload=_expected_payload(contract, settings)
    )


@router.post(
    "/{template_id}/instantiate",
    response_model=LandingTemplateInstantiateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def instantiate_landing_template(
    template_id: int,
    request: LandingTemplateInstantiateRequest,
    settings: Settings = Depends(get_settings),  # noqa: B008
    r2: R2Client = Depends(get_r2_client),  # noqa: B008
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008
) -> LandingTemplateInstantiateResponse:
    """Create and publish one complete product landing from staged R2 originals."""
    service = LandingTemplateInstantiationService(
        get_prisma(), r2, public_host=settings.r2_public_host
    )
    try:
        created = await service.instantiate(
            template_id,
            template_version=request.template_version,
            product=request.product.model_dump(),
            slug=request.landing.slug,
            banners=[item.model_dump() for item in request.banners],
            block_assets=[item.model_dump() for item in request.block_assets],
            actor=admin_user.subject,
        )
    except TemplateNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Landing template not found"
        ) from exc
    except TemplateVersionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "field": "template_version",
                "message": "La plantilla cambió; solicita nuevamente el contrato de creación.",
            },
        ) from exc
    except DuplicateSkuError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"field": "sku", "message": str(exc)},
        ) from exc
    except DuplicateSlugError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"field": "slug", "message": str(exc)},
        ) from exc
    except ProductValidationError as exc:
        raise _field_error(exc.field, exc.message) from exc
    except (LandingValidationError, ImageValidationError, VideoValidationError) as exc:
        raise _field_error(exc.field, exc.message) from exc
    except (ImagePipelineUnavailableError, OpaqueKeyGenerationError, VideoPipelineError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El procesamiento de archivos no está disponible temporalmente.",
        ) from exc

    return LandingTemplateInstantiateResponse(
        product_id=created.product_id,
        product_status="active",
        landing_id=created.landing_id,
        landing_status="published",
        slug=created.slug,
        public_path=f"/p/{created.slug}",
    )


@router.post("", response_model=LandingTemplateResponse, status_code=status.HTTP_201_CREATED)
async def save_landing_template(
    request: LandingTemplateSaveRequest,
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> LandingTemplateResponse:
    """Snapshot a landing's configuration and components under a name."""
    service = LandingTemplateService(get_prisma())
    try:
        saved = await service.save_template(
            request.landing_id,
            name=request.name,
            overwrite=request.overwrite,
            actor=admin_user.subject,
        )
    except LandingNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Landing not found"
        ) from exc
    except DuplicateTemplateNameError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "field": "name",
                "message": f"Ya existe una plantilla llamada «{exc.name}».",
                "template_id": exc.template_id,
            },
        ) from exc
    except LandingValidationError as exc:
        raise _field_error(exc.field, exc.message) from exc

    return _to_template_response(saved)


@router.delete("/{template_id}", response_model=LandingTemplateListResponse)
async def delete_landing_template(
    template_id: int,
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> LandingTemplateListResponse:
    """Remove a saved template. Landings already configured from it are untouched."""
    service = LandingTemplateService(get_prisma())
    try:
        await service.delete_template(template_id, actor=admin_user.subject)
    except TemplateNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Landing template not found"
        ) from exc

    templates = await service.list_templates()
    return LandingTemplateListResponse(
        templates=[_to_template_response(template) for template in templates]
    )
