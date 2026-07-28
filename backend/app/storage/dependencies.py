"""FastAPI dependency provider for the R2 object storage client.

Follows the same shape as `get_redis` / `get_geoip_resolver`: one process-wide
client built lazily from settings, overridable in tests through
`app.dependency_overrides[get_r2_client]`.

The boto3 client underneath opens no connection at construction time, so
building it lazily on the first upload request keeps application startup
independent of R2 reachability.
"""

from __future__ import annotations

from fastapi import Depends

from app.core.settings import Settings, get_settings
from app.storage.r2_client import R2Client, create_r2_client

_r2_client: R2Client | None = None


def get_r2_client(
    settings: Settings = Depends(get_settings),  # noqa: B008 (FastAPI DI convention)
) -> R2Client:
    """Return the process-wide `R2Client` bound to the configured bucket."""
    global _r2_client
    if _r2_client is None:
        _r2_client = R2Client(create_r2_client(settings), bucket=settings.r2_bucket)
    return _r2_client


def reset_r2_client() -> None:
    """Drop the cached client (used by tests that change R2 settings)."""
    global _r2_client
    _r2_client = None
