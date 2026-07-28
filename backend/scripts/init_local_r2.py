"""Create the local S3-compatible bucket the image pipeline uploads into.

Development bootstrap only. Cloudflare R2 buckets are provisioned once per
deployed environment, but a throwaway local MinIO container starts empty, so
banner uploads fail with the same non-sensitive "unavailable" response an R2
outage produces (Requirement 4.21) until the bucket in `R2_BUCKET` exists.

This script is idempotent: it creates the bucket when missing and applies an
anonymous read-only policy so `R2_PUBLIC_HOST` can serve variants the way
Cloudflare serves them in front of R2 (Requirement 4.19, 9.10).

Usage (PowerShell), against the settings already in `backend/.env`:

    python -m scripts.init_local_r2

Refuses to run unless `ENVIRONMENT` is `development` and the endpoint is
local, so it can never touch a real R2 bucket policy.
"""

from __future__ import annotations

import json
import sys
from urllib.parse import urlparse

from app.core.settings import get_settings
from app.storage.r2_client import create_r2_client

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "minio"}


def _public_read_policy(bucket: str) -> str:
    return json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket}/*"],
                }
            ],
        }
    )


def main() -> int:
    settings = get_settings()
    host = urlparse(settings.r2_endpoint).hostname or ""

    if settings.environment != "development" or host not in _LOCAL_HOSTS:
        print(
            "Refusing to run: this script only initializes a local development "
            f"endpoint (environment={settings.environment!r}, host={host!r}).",
            file=sys.stderr,
        )
        return 2

    client = create_r2_client(settings)
    existing = {bucket["Name"] for bucket in client.list_buckets().get("Buckets", [])}

    if settings.r2_bucket in existing:
        print(f"Bucket '{settings.r2_bucket}' already exists.")
    else:
        client.create_bucket(Bucket=settings.r2_bucket)
        print(f"Bucket '{settings.r2_bucket}' created.")

    client.put_bucket_policy(
        Bucket=settings.r2_bucket, Policy=_public_read_policy(settings.r2_bucket)
    )
    print(f"Anonymous read policy applied to '{settings.r2_bucket}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
