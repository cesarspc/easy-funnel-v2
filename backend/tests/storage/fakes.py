"""In-process R2-compatible test double.

Mirrors the `R2Client` interface (`put_bytes`/`get_bytes`/`delete`/`exists`)
with a plain in-memory dict, so image-pipeline unit tests don't need a running
MinIO/R2-compatible instance. Integration tests against a real endpoint
live in tests/storage/test_r2_client.py (see docs/testing.md).
"""

from __future__ import annotations


class FakeR2Client:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.content_types: dict[str, str] = {}

    async def put_bytes(self, key: str, data: bytes, *, content_type: str) -> None:
        self.objects[key] = data
        self.content_types[key] = content_type

    async def get_bytes(self, key: str) -> bytes:
        return self.objects[key]

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)
        self.content_types.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self.objects


class FakeUnavailableR2Client:
    """Test double simulating an unreachable R2 endpoint (upload outage)."""

    async def put_bytes(self, key: str, data: bytes, *, content_type: str) -> None:
        raise ConnectionError("R2 is unavailable")

    async def get_bytes(self, key: str) -> bytes:
        raise ConnectionError("R2 is unavailable")

    async def delete(self, key: str) -> None:
        raise ConnectionError("R2 is unavailable")

    async def exists(self, key: str) -> bool:
        raise ConnectionError("R2 is unavailable")
