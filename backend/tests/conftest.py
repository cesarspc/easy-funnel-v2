"""Shared fixtures and test environment for the whole backend test suite.

`db` and `requires_database` live here (rather than under `tests/db/`) so
any test module — not just database-focused ones — can depend on a real
database connection. Requires a throwaway PostgreSQL instance reachable at
`DATABASE_URL` (see docs/testing.md); database-dependent tests are skipped
automatically when it is not set.

Test environment (Requirement 9.3): the suite needs a complete, *synthetic*
`Settings` environment so the FastAPI app can be constructed by router/e2e
tests. Those values live in `_SYNTHETIC_TEST_ENV` below — tracked in git —
so a clean checkout is reproducible and the suite never depends on a
developer's local, untracked `.env.test`. Precedence, highest first:

1. real process environment (CI secrets, `DATABASE_URL` for a local container)
2. `backend/.env.test`, when present (local overrides such as a custom port)
3. `_SYNTHETIC_TEST_ENV` (placeholders; never real credentials)

`DATABASE_URL` is deliberately *not* defaulted: it must point at a real
throwaway database, and its absence is what makes database-backed tests skip
instead of failing against an imaginary server.

Variables are only ever set here with `setdefault`, and tests that assert on
`Settings` parsing itself isolate themselves from the process environment
(see `tests/core/test_settings.py`).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from prisma import Prisma

_BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Synthetic, non-secret placeholders for every required `Settings` field
# except DATABASE_URL. Redis uses the application's canonical Upstash REST
# variable names (`app.core.settings.Settings`) so the test environment and
# the application speak one vocabulary; tests that exercise rate limiting
# inject the in-process double from `tests/redis/fakes.py` instead of
# reaching this endpoint (docs/testing.md -> Redis rate-limit tests).
_SYNTHETIC_TEST_ENV = {
    "REDIS_URL": "redis://localhost:6379/15",
    "R2_ENDPOINT": "https://test.r2.cloudflarestorage.com",
    "R2_ACCESS_KEY_ID": "test-access-key",
    "R2_SECRET_ACCESS_KEY": "test-secret-key",
    "R2_BUCKET": "test-bucket",
    "R2_PUBLIC_HOST": "https://test-images.example.com",
    "JWT_SECRET": "test-signing-secret-not-a-real-credential-000000",
    "GEOIP_DATABASE_PATH": str(
        _BACKEND_ROOT.parent / "infrastructure" / "geoip" / "GeoLite2-Country.mmdb"
    ),
}


def _load_env_file(path: Path) -> None:
    """Apply `KEY=value` lines from `path` without overriding the real env."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            continue
        key = key.strip()
        if key:
            os.environ.setdefault(key, value.strip())


def _apply_test_environment() -> None:
    """Populate the process environment for the test session (see module docs)."""
    _load_env_file(_BACKEND_ROOT / ".env.test")
    for key, value in _SYNTHETIC_TEST_ENV.items():
        os.environ.setdefault(key, value)


_apply_test_environment()

requires_database = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL is not set; skipping database integration tests",
)


@pytest_asyncio.fixture
async def db() -> AsyncIterator[Prisma]:
    client = Prisma()
    await client.connect()
    try:
        yield client
    finally:
        await client.disconnect()
