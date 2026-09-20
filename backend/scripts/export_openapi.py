"""Write the API's OpenAPI document to a file without running the service.

The schema is a pure function of the route table, so nothing here starts a
server or opens a connection: FastAPI builds the document from the imported
application object, and the lifespan hook that would reach PostgreSQL, Redis and
object storage never runs. That is what makes the published reference buildable
in CI, on a laptop, or inside a container that has no database in front of it.

`Settings` is still constructed at import time, so the module fills in synthetic
placeholders for the variables it requires. They are deliberately obvious
non-secrets, they only have to parse, and `setdefault` means a real environment
always wins — the same precedence `tests/conftest.py` uses.

Usage (from `backend/`):

    python -m scripts.export_openapi                     # -> api-docs/openapi.json
    python -m scripts.export_openapi --output spec.json
    python -m scripts.export_openapi --check             # CI: fail if stale

Or, with no local Python environment at all, from the repository root:

    docker compose run --rm --no-deps backend \\
        python -m scripts.export_openapi --stdout > api-docs/openapi.json

`sh docs.sh build` picks whichever of those two paths is available.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_ROOT.parent
_DEFAULT_OUTPUT = _REPO_ROOT / "api-docs" / "openapi.json"

# Placeholders that only need to satisfy `Settings` validation. No connection is
# ever opened with them, and a real environment variable always takes priority.
_SCHEMA_ONLY_ENV = {
    "DATABASE_URL": "postgresql://schema:schema@localhost:5432/schema",
    "REDIS_URL": "redis://localhost:6379/0",
    "JWT_SECRET": "openapi-export-placeholder-not-a-real-secret",
    "GEOIP_DATABASE_PATH": "/nonexistent/GeoLite2-Country.mmdb",
    "S3_ENDPOINT": "https://storage.invalid",
    "S3_ACCESS_KEY_ID": "schema-only",
    "S3_SECRET_ACCESS_KEY": "schema-only",
    "S3_BUCKET": "schema-only",
    "S3_PUBLIC_BASE_URL": "https://images.invalid",
    "ENVIRONMENT": "development",
}


def build_schema() -> dict:
    """Import the application and return its OpenAPI document."""
    for key, value in _SCHEMA_ONLY_ENV.items():
        os.environ.setdefault(key, value)

    # Imported here, after the environment is prepared, because importing
    # `app.main` constructs the application and therefore reads Settings.
    if str(_BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(_BACKEND_ROOT))
    from app.main import app

    return app.openapi()


def _serialize(schema: dict) -> str:
    # Sorted keys and a trailing newline keep the committed document diffable:
    # a route change should show up as a route change, not as a reordering.
    return json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=_DEFAULT_OUTPUT,
        help="Where to write the document (default: api-docs/openapi.json).",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Write to standard output instead of a file.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if the file on disk differs from the current routes.",
    )
    args = parser.parse_args(argv)

    payload = _serialize(build_schema())

    if args.stdout:
        sys.stdout.write(payload)
        return 0

    if args.check:
        if not args.output.exists():
            print(f"{args.output} does not exist; run `python -m scripts.export_openapi`.")
            return 1
        if args.output.read_text(encoding="utf-8") != payload:
            print(
                f"{args.output} is out of date with the route table; "
                "re-run `python -m scripts.export_openapi`."
            )
            return 1
        print(f"{args.output} matches the current routes.")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding="utf-8")
    schema = json.loads(payload)
    print(f"Wrote {args.output.relative_to(_REPO_ROOT)}")
    print(f"  OpenAPI {schema['openapi']} · {schema['info']['title']} {schema['info']['version']}")
    print(f"  {len(schema.get('paths', {}))} paths documented")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
