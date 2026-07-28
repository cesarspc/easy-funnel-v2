"""Cloudflare R2 object storage client and helpers.

R2 is S3-compatible, so this module uses boto3's S3 client pointed at the
R2 endpoint (Requirement 1.11, 4.7, 4.19).
"""

from app.storage.dependencies import get_r2_client, reset_r2_client
from app.storage.r2_client import (
    R2Client,
    create_r2_client,
    original_object_key,
    variant_object_key,
    variant_public_url,
)

__all__ = [
    "R2Client",
    "create_r2_client",
    "get_r2_client",
    "reset_r2_client",
    "original_object_key",
    "variant_object_key",
    "variant_public_url",
]
