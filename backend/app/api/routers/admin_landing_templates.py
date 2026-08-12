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

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.auth_dependencies import require_admin
from app.db.client import get_prisma
from app.domains.landings.errors import LandingNotFoundError, LandingValidationError
from app.services.landing_template_service import (
    DuplicateTemplateNameError,
    LandingTemplateService,
    TemplateNotFoundError,
)

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
