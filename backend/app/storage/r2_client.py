"""Cloudflare R2 client wrapper (S3-compatible via boto3).

Reads connection settings from `app.core.settings.Settings`. Object key
layout follows design.md -> Deployment and Operations Design:
    /originals/{opaque_key}.{ext}
    /variants/{opaque_key}/{width}.{webp|jpg}
"""

from __future__ import annotations

import asyncio
from functools import partial
from typing import Any

import boto3

from app.core.settings import Settings

IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"


def create_r2_client(settings: Settings) -> Any:
    """Build a boto3 S3 client pointed at the configured R2 endpoint."""
    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )


def original_object_key(opaque_key: str, extension: str) -> str:
    return f"originals/{opaque_key}.{extension}"


def variant_object_key(opaque_key: str, width: int, format_: str) -> str:
    ext = "jpg" if format_ == "jpeg" else format_
    return f"variants/{opaque_key}/{width}.{ext}"


def variant_public_url(public_host: str, opaque_key: str, width: int, format_: str) -> str:
    """Return the public, immutable URL for one variant.

    The path is the variant's own object key, so `R2_PUBLIC_HOST` can point
    straight at the bucket (Cloudflare in front of R2, or a local MinIO
    container in development) and serve the object with no path-rewrite rule
    in between. The opaque key in the path is the version token, so the URL
    stays immutable: replacing an image produces a new key rather than
    mutating an existing URL.
    """
    return f"{public_host.rstrip('/')}/{variant_object_key(opaque_key, width, format_)}"


def video_object_key(opaque_key: str) -> str:
    return f"videos/{opaque_key}/video.mp4"


def video_poster_object_key(opaque_key: str) -> str:
    return f"videos/{opaque_key}/poster.webp"


def object_public_url(public_host: str, object_key: str) -> str:
    return f"{public_host.rstrip('/')}/{object_key}"


class R2Client:
    """Thin wrapper over the boto3 S3 client scoped to one bucket.

    Kept intentionally small: `put_bytes`/`delete`/`exists` are the only
    operations the image pipeline needs. Callers never touch the boto3
    client directly, so a future storage backend swap only touches this
    module.
    """

    def __init__(self, boto3_client: Any, *, bucket: str) -> None:
        self._client = boto3_client
        self._bucket = bucket

    async def _run(self, func: Any, /, **kwargs: Any) -> Any:
        # boto3 is synchronous; offload each call to a worker thread so it
        # never blocks the event loop.
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, partial(func, **kwargs))

    async def put_bytes(self, key: str, data: bytes, *, content_type: str) -> None:
        await self._run(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            # Every public media object is stored below an opaque, never-reused key.
            # Preserve Cloudflare's edge caching while also advertising the
            # same immutable policy to browsers and direct R2 consumers.
            CacheControl=IMMUTABLE_CACHE_CONTROL,
        )

    async def delete(self, key: str) -> None:
        await self._run(self._client.delete_object, Bucket=self._bucket, Key=key)

    async def get_bytes(self, key: str) -> bytes:
        """Read one object back. Only the edge-color backfill needs this."""
        response = await self._run(self._client.get_object, Bucket=self._bucket, Key=key)
        body = response["Body"]
        return bytes(await self._run(body.read))

    async def exists(self, key: str) -> bool:
        try:
            await self._run(self._client.head_object, Bucket=self._bucket, Key=key)
            return True
        except Exception:
            return False
