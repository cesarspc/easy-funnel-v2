"""Create or refresh an Administrator account (Requirement 7.1, 7.2, 10.10).

Local/bootstrap maintenance only: the platform has no self-service admin
signup, so the first Administrator — and any password refresh for a
development environment — is created through this script against the
database in `DATABASE_URL`.

The password is only ever stored as an Argon2id hash, and the mutation is
recorded in `audit_log` like every other administrative change.

Usage (PowerShell):

    $env:ADMIN_PASSWORD = "..."
    python -m scripts.seed_admin --username local-admin

Passing `--password` inline is supported for convenience, but prefers
`ADMIN_PASSWORD` so the value stays out of shell history.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from app.core.password_hashing import hash_password
from app.db.client import connect_db, disconnect_db, get_db

MIN_PASSWORD_LENGTH = 12


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or refresh an Administrator account.")
    parser.add_argument("--username", required=True, help="Administrator username.")
    parser.add_argument(
        "--password",
        default=None,
        help="Administrator password. Defaults to the ADMIN_PASSWORD environment variable.",
    )
    parser.add_argument("--role", default="admin", help="Role stored on the account.")
    return parser.parse_args(argv)


async def seed_admin(*, username: str, password: str, role: str = "admin") -> str:
    """Create or refresh `username`; returns "created" or "refreshed"."""
    await connect_db()
    db = get_db()
    try:
        existing = await db.adminuser.find_unique(where={"username": username})
        password_hash = hash_password(password)

        if existing is None:
            await db.adminuser.create(
                {"username": username, "passwordHash": password_hash, "role": role}
            )
            outcome = "created"
        else:
            await db.adminuser.update(
                where={"username": username},
                data={"passwordHash": password_hash, "role": role},
            )
            outcome = "refreshed"

        await db.auditlog.create(
            data={
                "actor": "seed_admin_script",
                "action": f"admin_user.{outcome}",
                "targetType": "admin_user",
                "targetId": username,
                "result": "success",
            }
        )
        return outcome
    finally:
        await disconnect_db()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    password = args.password or os.getenv("ADMIN_PASSWORD")

    if not password:
        print("A password is required: pass --password or set ADMIN_PASSWORD.", file=sys.stderr)
        return 2
    if len(password) < MIN_PASSWORD_LENGTH:
        print(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
            file=sys.stderr,
        )
        return 2

    outcome = asyncio.run(seed_admin(username=args.username, password=password, role=args.role))
    print(f"Administrator '{args.username}' {outcome}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
