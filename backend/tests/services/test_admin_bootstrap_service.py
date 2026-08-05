"""Tests for `ensure_admin_user` (Requirements 7.1, 7.2, 7.6, 10.10).

Exercises the provisioning contract shared by the application startup hook and
`scripts.seed_admin`: create-when-missing, non-destructive by default, explicit
reset when asked, password never persisted in plaintext, and every write
audited. Uses a real Prisma-backed database (see tests/conftest.py).
"""

from __future__ import annotations

import uuid

import pytest
from app.core.password_hashing import verify_password
from app.services.admin_bootstrap_service import (
    MIN_PASSWORD_LENGTH,
    AdminPasswordTooShortError,
    ensure_admin_user,
)
from prisma import Prisma

from tests.db.conftest import requires_database

_VALID_PASSWORD = "a-sufficiently-long-password"
_OTHER_PASSWORD = "an-entirely-different-password"


def _unique_username() -> str:
    return f"bootstrap-{uuid.uuid4().hex[:12]}"


@requires_database
class TestEnsureAdminUser:
    async def test_creates_the_account_when_missing(self, db: Prisma) -> None:
        username = _unique_username()

        outcome = await ensure_admin_user(db, username=username, password=_VALID_PASSWORD)

        assert outcome == "created"
        stored = await db.adminuser.find_unique(where={"username": username})
        assert stored is not None
        assert stored.role == "admin"

    async def test_stores_only_a_verifiable_hash_never_plaintext(self, db: Prisma) -> None:
        username = _unique_username()

        await ensure_admin_user(db, username=username, password=_VALID_PASSWORD)

        stored = await db.adminuser.find_unique(where={"username": username})
        assert stored is not None
        assert _VALID_PASSWORD not in stored.passwordHash
        assert verify_password(stored.passwordHash, _VALID_PASSWORD) is True

    async def test_existing_account_is_left_untouched_by_default(self, db: Prisma) -> None:
        """A restart must not revert a rotated password back to the env value."""
        username = _unique_username()
        await ensure_admin_user(db, username=username, password=_VALID_PASSWORD)
        before = await db.adminuser.find_unique(where={"username": username})
        assert before is not None

        outcome = await ensure_admin_user(db, username=username, password=_OTHER_PASSWORD)

        assert outcome == "unchanged"
        after = await db.adminuser.find_unique(where={"username": username})
        assert after is not None
        assert after.passwordHash == before.passwordHash
        assert verify_password(after.passwordHash, _VALID_PASSWORD) is True
        assert verify_password(after.passwordHash, _OTHER_PASSWORD) is False

    async def test_reset_existing_replaces_the_stored_hash(self, db: Prisma) -> None:
        username = _unique_username()
        await ensure_admin_user(db, username=username, password=_VALID_PASSWORD)

        outcome = await ensure_admin_user(
            db, username=username, password=_OTHER_PASSWORD, reset_existing=True
        )

        assert outcome == "password_reset"
        stored = await db.adminuser.find_unique(where={"username": username})
        assert stored is not None
        assert verify_password(stored.passwordHash, _OTHER_PASSWORD) is True
        assert verify_password(stored.passwordHash, _VALID_PASSWORD) is False

    async def test_repeated_calls_create_exactly_one_account(self, db: Prisma) -> None:
        username = _unique_username()

        for _ in range(3):
            await ensure_admin_user(db, username=username, password=_VALID_PASSWORD)

        matches = await db.adminuser.find_many(where={"username": username})
        assert len(matches) == 1

    async def test_creation_is_audited(self, db: Prisma) -> None:
        username = _unique_username()

        await ensure_admin_user(db, username=username, password=_VALID_PASSWORD)

        entries = await db.auditlog.find_many(
            where={"targetType": "admin_user", "targetId": username}
        )
        assert [entry.action for entry in entries] == ["admin_user.created"]
        assert entries[0].result == "success"

    async def test_unchanged_outcome_writes_no_audit_entry(self, db: Prisma) -> None:
        username = _unique_username()
        await ensure_admin_user(db, username=username, password=_VALID_PASSWORD)

        await ensure_admin_user(db, username=username, password=_VALID_PASSWORD)

        entries = await db.auditlog.find_many(
            where={"targetType": "admin_user", "targetId": username}
        )
        assert [entry.action for entry in entries] == ["admin_user.created"]

    async def test_reset_is_audited_separately_from_creation(self, db: Prisma) -> None:
        username = _unique_username()
        await ensure_admin_user(db, username=username, password=_VALID_PASSWORD)

        await ensure_admin_user(
            db, username=username, password=_OTHER_PASSWORD, reset_existing=True
        )

        entries = await db.auditlog.find_many(
            where={"targetType": "admin_user", "targetId": username},
            order={"createdAt": "asc"},
        )
        assert [entry.action for entry in entries] == [
            "admin_user.created",
            "admin_user.password_reset",
        ]


class TestPasswordLengthGuard:
    """Length is rejected before any database work, so no fixture is needed."""

    @pytest.mark.parametrize("length", [0, 1, MIN_PASSWORD_LENGTH - 1])
    async def test_short_passwords_are_rejected(self, length: int) -> None:
        with pytest.raises(AdminPasswordTooShortError):
            await ensure_admin_user(
                None,  # type: ignore[arg-type]  # never reached
                username="unused",
                password="x" * length,
            )
