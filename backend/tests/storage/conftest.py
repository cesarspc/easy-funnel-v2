"""Shared fixtures for R2 client integration tests.

Requires an S3-compatible endpoint reachable at `R2_TEST_ENDPOINT` (e.g. a
local MinIO container; see docs/testing.md). Skipped automatically when not
set.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import AsyncIterator

import boto3
import pytest
import pytest_asyncio
from app.storage.r2_client import R2Client

requires_r2 = pytest.mark.skipif(
    not os.environ.get("R2_TEST_ENDPOINT"),
    reason="R2_TEST_ENDPOINT is not set; skipping R2 integration tests",
)

_TEST_BUCKET = "cod-test-bucket"


@pytest_asyncio.fixture
async def r2_client() -> AsyncIterator[R2Client]:
    boto_client = boto3.client(
        "s3",
        endpoint_url=os.environ["R2_TEST_ENDPOINT"],
        aws_access_key_id=os.environ.get("R2_TEST_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=os.environ.get("R2_TEST_SECRET_KEY", "minioadmin"),
        region_name="auto",
    )
    with contextlib.suppress(Exception):
        boto_client.create_bucket(Bucket=_TEST_BUCKET)  # already exists from a prior test run

    yield R2Client(boto_client, bucket=_TEST_BUCKET)
