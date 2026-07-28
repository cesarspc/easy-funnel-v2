"""Migration harness integration tests (Requirements 1.10, 9.19).

Applies every checked-in migration to a throwaway PostgreSQL database via
`prisma migrate deploy` (the same one-off, forward-only entrypoint used in
production — never ad-hoc auto-create) and asserts a clean run, alongside a
`prisma validate` check. Requires `DATABASE_URL` to point at a disposable
database; see docs/testing.md for the local Docker Postgres setup.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tests.db.conftest import requires_database

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCHEMA_PATH = "prisma/schema.prisma"


def _run_prisma(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "prisma", *args, f"--schema={_SCHEMA_PATH}"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


@requires_database
class TestMigrationHarness:
    def test_schema_validates(self) -> None:
        result = _run_prisma("validate")

        assert result.returncode == 0, result.stdout + result.stderr
        assert "is valid" in result.stdout

    def test_migrate_deploy_applies_cleanly_to_a_throwaway_database(self) -> None:
        reset_result = _run_prisma("migrate", "reset", "--force", "--skip-generate")
        assert reset_result.returncode == 0, reset_result.stdout + reset_result.stderr

        deploy_result = _run_prisma("migrate", "deploy")

        assert deploy_result.returncode == 0, deploy_result.stdout + deploy_result.stderr
        assert "error" not in deploy_result.stdout.lower()

    def test_migrate_deploy_is_idempotent(self) -> None:
        first = _run_prisma("migrate", "deploy")
        second = _run_prisma("migrate", "deploy")

        assert first.returncode == 0, first.stdout + first.stderr
        assert second.returncode == 0, second.stdout + second.stderr
        assert "No pending migrations" in second.stdout or "up to date" in second.stdout.lower()
