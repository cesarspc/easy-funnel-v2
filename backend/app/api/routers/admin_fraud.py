"""Admin Fraud API router: config, blacklist, and GeoIP rule endpoints.

Requirements 6.6-6.8, 6.20-6.24, 8.10, 10.9, 10.10. Thin layer over
`FraudSettingsService`, which owns validation, normalization, and audit
records.

Error mapping, applied uniformly:

- `FraudValidationError` -> `422` with `{"field", "message"}` so the dashboard
  can bind the message to the control that produced it (Requirement 8.19)
- `DuplicateBlacklistEntryError` / `DuplicateGeoIpRuleError` -> `409`, existing
  row unchanged (Requirement 6.7)
- `BlacklistEntryNotFoundError` / `GeoIpRuleNotFoundError` -> `404`
- `ConfigNotFoundError` -> `500` (the singleton row is seeded by migration, so
  its absence is a deployment fault, not caller input)

Prisma models never cross the API boundary (Requirement 10.3): every response
is a snake_case Pydantic model matching the admin API contract the SPA
consumes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.auth_dependencies import require_admin
from app.db.client import get_prisma
from app.domains.fraud.errors import (
    BlacklistEntryNotFoundError,
    ConfigNotFoundError,
    DuplicateBlacklistEntryError,
    DuplicateGeoIpRuleError,
    FraudValidationError,
    GeoIpRuleNotFoundError,
)
from app.domains.orders.errors import OrderValidationError
from app.services.fraud_settings_service import FraudSettingsService

router = APIRouter(prefix="/api/admin/fraud", tags=["admin", "fraud"])


class FraudConfigResponse(BaseModel):
    id: int
    duplicate_window_hours: int
    duplicate_match_fields: list[str]
    rate_limit_max: int
    rate_limit_window_minutes: int
    banned_cities: list[str]


class FraudConfigUpdateRequest(BaseModel):
    duplicate_window_hours: int | None = None
    duplicate_match_fields: list[str] | None = None
    rate_limit_max: int | None = None
    rate_limit_window_minutes: int | None = None
    banned_cities: list[str] | None = None


class BlacklistEntryResponse(BaseModel):
    id: int
    entry_type: str
    value_normalized: str
    reason: str
    created_at: str


class BlacklistEntryListResponse(BaseModel):
    entries: list[BlacklistEntryResponse]


class BlacklistEntryRequest(BaseModel):
    entry_type: str
    value_normalized: str
    reason: str


class GeoIpRuleResponse(BaseModel):
    id: int
    location_code: str
    action: str
    enabled: bool
    created_at: str
    updated_at: str


class GeoIpRuleListResponse(BaseModel):
    rules: list[GeoIpRuleResponse]


class GeoIpRuleCreateRequest(BaseModel):
    location_code: str
    action: str
    enabled: bool = True


class GeoIpRuleUpdateRequest(BaseModel):
    location_code: str | None = None
    action: str | None = None
    enabled: bool | None = None


def _field_error(field: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"field": field, "message": message},
    )


def _config_response(config) -> FraudConfigResponse:  # type: ignore[no-untyped-def]
    return FraudConfigResponse(
        id=config.id,
        duplicate_window_hours=config.duplicateWindowHours,
        duplicate_match_fields=list(config.duplicateMatchFields or []),
        rate_limit_max=config.rateLimitMax,
        rate_limit_window_minutes=config.rateLimitWindowMinutes,
        banned_cities=list(getattr(config, "bannedCities", None) or []),
    )


def _blacklist_response(entry) -> BlacklistEntryResponse:  # type: ignore[no-untyped-def]
    return BlacklistEntryResponse(
        id=entry.id,
        entry_type=entry.entryType,
        value_normalized=entry.valueNormalized,
        reason=entry.reason,
        created_at=entry.createdAt.isoformat(),
    )


def _geoip_response(rule) -> GeoIpRuleResponse:  # type: ignore[no-untyped-def]
    return GeoIpRuleResponse(
        id=rule.id,
        location_code=rule.locationCode,
        action=rule.action,
        enabled=rule.enabled,
        created_at=rule.createdAt.isoformat(),
        updated_at=rule.updatedAt.isoformat(),
    )


def _missing_config() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Fraud configuration not found",
    )


@router.get("/config", response_model=FraudConfigResponse)
async def get_fraud_config(
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> FraudConfigResponse:
    """Return the current Fraud_Configuration."""
    service = FraudSettingsService(get_prisma())
    try:
        return _config_response(await service.get_config())
    except ConfigNotFoundError as exc:
        raise _missing_config() from exc


@router.put("/config", response_model=FraudConfigResponse)
async def update_fraud_config(
    request: FraudConfigUpdateRequest,
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> FraudConfigResponse:
    """Update the Fraud_Configuration; omitted fields keep their stored value.

    Applies to subsequent submissions immediately. A rejected value never
    replaces the active configuration (Requirement 6.24).
    """
    service = FraudSettingsService(get_prisma())
    try:
        updated = await service.update_config(
            duplicate_window_hours=request.duplicate_window_hours,
            duplicate_match_fields=request.duplicate_match_fields,
            rate_limit_max=request.rate_limit_max,
            rate_limit_window_minutes=request.rate_limit_window_minutes,
            banned_cities=request.banned_cities,
            actor=admin_user.subject,
        )
    except FraudValidationError as exc:
        raise _field_error(exc.field, exc.message) from exc
    except OrderValidationError as exc:
        raise _field_error(exc.field, exc.message) from exc
    except ConfigNotFoundError as exc:
        raise _missing_config() from exc

    return _config_response(updated)


@router.get("/blacklist", response_model=BlacklistEntryListResponse)
async def list_blacklist(
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> BlacklistEntryListResponse:
    """List every Manual_Blacklist entry."""
    service = FraudSettingsService(get_prisma())
    entries = await service.list_blacklist()
    return BlacklistEntryListResponse(entries=[_blacklist_response(entry) for entry in entries])


@router.post(
    "/blacklist",
    response_model=BlacklistEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_blacklist_entry(
    request: BlacklistEntryRequest,
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> BlacklistEntryResponse:
    """Add a Manual_Blacklist entry.

    Phone values are normalized to the fraud-check comparison key and IP values
    to their canonical form, so the stored value may differ from the submitted
    text (Requirement 6.6).
    """
    service = FraudSettingsService(get_prisma())
    try:
        entry = await service.add_blacklist_entry(
            entry_type=request.entry_type,
            value=request.value_normalized,
            reason=request.reason,
            actor=admin_user.subject,
        )
    except FraudValidationError as exc:
        raise _field_error(exc.field, exc.message) from exc
    except OrderValidationError as exc:
        # Phone normalization rejects the value with the orders domain's own
        # field-specific error; report it against the field that carried it.
        raise _field_error("value_normalized", exc.message) from exc
    except DuplicateBlacklistEntryError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return _blacklist_response(entry)


@router.delete("/blacklist/{entry_id}")
async def remove_blacklist_entry(
    entry_id: int,
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> dict[str, str]:
    """Remove a Manual_Blacklist entry; historical Fraud_Flags are preserved."""
    service = FraudSettingsService(get_prisma())
    try:
        await service.remove_blacklist_entry(entry_id, actor=admin_user.subject)
    except BlacklistEntryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found"
        ) from exc

    return {"message": "Entry removed"}


@router.get("/geoip-rules", response_model=GeoIpRuleListResponse)
async def list_geoip_rules(
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> GeoIpRuleListResponse:
    """List every GeoIP_Rule, enabled or not."""
    service = FraudSettingsService(get_prisma())
    rules = await service.list_geoip_rules()
    return GeoIpRuleListResponse(rules=[_geoip_response(rule) for rule in rules])


@router.post(
    "/geoip-rules",
    response_model=GeoIpRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_geoip_rule(
    request: GeoIpRuleCreateRequest,
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> GeoIpRuleResponse:
    """Create a GeoIP_Rule.

    Both `flag` and `block` produce a reviewable `flagged_fraud` order; neither
    action discards a submission (Requirement 6.15).
    """
    service = FraudSettingsService(get_prisma())
    try:
        rule = await service.create_geoip_rule(
            location_code=request.location_code,
            action=request.action,
            enabled=request.enabled,
            actor=admin_user.subject,
        )
    except FraudValidationError as exc:
        raise _field_error(exc.field, exc.message) from exc
    except DuplicateGeoIpRuleError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return _geoip_response(rule)


@router.patch("/geoip-rules/{rule_id}", response_model=GeoIpRuleResponse)
async def update_geoip_rule(
    rule_id: int,
    request: GeoIpRuleUpdateRequest,
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> GeoIpRuleResponse:
    """Update a GeoIP_Rule; omitted fields keep their stored value."""
    service = FraudSettingsService(get_prisma())
    try:
        rule = await service.update_geoip_rule(
            rule_id,
            location_code=request.location_code,
            action=request.action,
            enabled=request.enabled,
            actor=admin_user.subject,
        )
    except FraudValidationError as exc:
        raise _field_error(exc.field, exc.message) from exc
    except DuplicateGeoIpRuleError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except GeoIpRuleNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found") from exc

    return _geoip_response(rule)


@router.delete("/geoip-rules/{rule_id}")
async def delete_geoip_rule(
    rule_id: int,
    admin_user=Depends(require_admin),  # type: ignore  # noqa: B008 (FastAPI DI)
) -> dict[str, str]:
    """Delete a GeoIP_Rule; historical Fraud_Flags are preserved."""
    service = FraudSettingsService(get_prisma())
    try:
        await service.delete_geoip_rule(rule_id, actor=admin_user.subject)
    except GeoIpRuleNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found") from exc

    return {"message": "Rule deleted"}
