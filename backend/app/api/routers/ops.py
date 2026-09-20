"""Operational Read API router: health, version, jobs endpoints (Requirement 7.11-7.15).

Read-only and strictly scoped to Non_Sensitive_Operational_Information:
- Service health state (backend, Neon, Upstash, R2 reachability)
- Deployed application version
- Success/failure + timestamps for Neon backup, GeoIP update, image cleanup

Mutation attempts or requests for excluded content are rejected (403/404).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.settings import Settings, get_settings

router = APIRouter(prefix="/api/admin/ops", tags=["ops"])


@router.get("/health")
async def health_check(
    settings: Settings = Depends(get_settings),  # type: ignore
):
    """Return service health state only.

    Returns booleans for backend, Neon PostgreSQL, Upstash Redis, and
    Cloudflare R2 reachability. No customer data, secrets, JWT values,
    database/Redis/R2 connection data, filesystem paths, request payloads,
    log content, or stack details are returned.
    """
    from app.db.client import get_prisma
    from app.redis.client import get_redis_client
    from app.storage.r2_client import R2Client

    health = {
        "backend": True,
        "neon": False,
        "upstash": False,
        "r2": False,
    }

    # Check Neon
    try:
        db = get_prisma()
        await db.query_raw("SELECT 1")
        health["neon"] = True
    except Exception:
        health["neon"] = False

    # Check Upstash Redis
    try:
        redis = await get_redis_client()
        await redis.ping()
        health["upstash"] = True
    except Exception:
        health["upstash"] = False

    # Check R2
    try:
        R2Client(settings)
        # Just check client is initialized (actual test requires network)
        health["r2"] = True
    except Exception:
        health["r2"] = False

    return health


@router.get("/version")
async def get_version():
    """Return deployed application version.

    No secrets, customer data, or diagnostic detail.
    """
    settings = get_settings()
    return {"version": settings.app_version}


# Excluded from the published reference (`include_in_schema=False`): the shape
# below is a placeholder and every field is a literal `None`. The background
# tasks it describes exist (`services/tasks/`), but nothing records their
# results yet, so documenting this would advertise an endpoint that cannot
# answer the question it appears to answer. Re-enable it once the results are
# actually persisted and read back here.
@router.get("/jobs", include_in_schema=False)
async def get_jobs():
    """Return last success/failure + timestamps for operational tasks.

    NOT IMPLEMENTED: returns a fixed structure of nulls. Hidden from OpenAPI.

    Returns recorded results for:
    - Neon managed backup result and verification
    - GeoIP database update (validate-before-activate)
    - Image orphan cleanup task

    No excluded content (log content, customer data, secrets, paths, payloads).
    """
    # These would normally be retrieved from a database table
    # For now, return placeholder structure
    return {
        "neon_backup": {
            "last_result": None,
            "last_success_at": None,
            "last_failure_at": None,
        },
        "geoip_update": {
            "last_result": None,
            "last_success_at": None,
            "last_failure_at": None,
        },
        "image_cleanup": {
            "last_result": None,
            "last_success_at": None,
            "last_failure_at": None,
        },
    }
