"""Integration tests for R2Client against a real S3-compatible endpoint
(local MinIO; see tests/storage/conftest.py)."""

from __future__ import annotations

import uuid
from typing import Any

from app.storage.r2_client import IMMUTABLE_CACHE_CONTROL, R2Client

from tests.storage.conftest import requires_r2


class RecordingS3Client:
    def __init__(self) -> None:
        self.put_kwargs: dict[str, Any] | None = None

    def put_object(self, **kwargs: Any) -> None:
        self.put_kwargs = kwargs


async def test_put_advertises_immutable_browser_and_edge_caching() -> None:
    boto_client = RecordingS3Client()
    r2_client = R2Client(boto_client, bucket="images")

    await r2_client.put_bytes("variants/opaque/480.webp", b"image", content_type="image/webp")

    assert boto_client.put_kwargs is not None
    assert boto_client.put_kwargs["CacheControl"] == IMMUTABLE_CACHE_CONTROL


@requires_r2
class TestR2ClientPutGetDelete:
    async def test_put_then_exists_is_true(self, r2_client: R2Client) -> None:
        key = f"test/{uuid.uuid4().hex}.bin"

        await r2_client.put_bytes(key, b"hello r2", content_type="application/octet-stream")

        assert await r2_client.exists(key) is True

    async def test_delete_then_exists_is_false(self, r2_client: R2Client) -> None:
        key = f"test/{uuid.uuid4().hex}.bin"
        await r2_client.put_bytes(key, b"hello r2", content_type="application/octet-stream")

        await r2_client.delete(key)

        assert await r2_client.exists(key) is False

    async def test_exists_is_false_for_a_never_written_key(self, r2_client: R2Client) -> None:
        key = f"test/never-written-{uuid.uuid4().hex}.bin"

        assert await r2_client.exists(key) is False

    async def test_delete_of_an_already_missing_key_does_not_raise(
        self, r2_client: R2Client
    ) -> None:
        key = f"test/missing-{uuid.uuid4().hex}.bin"

        await r2_client.delete(key)  # must not raise
