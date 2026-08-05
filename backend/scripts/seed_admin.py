"""Create or refresh an Administrator account (Requirement 7.1, 7.2, 10.10).

Local/bootstrap maintenance entry point. The provisioning logic itself lives in
`app.services.admin_bootstrap_service` so this script and the application
startup hook (`ADMIN_USERNAME` / `ADMIN_PASSWORD`) cannot drift apart; this
module only owns argument parsing and the database connection lifecycle.

Unlike startup — which leaves an existing account alone — this script rewrites
the password of an existing account by default, because that is the explicit
intent of running it by hand. Pass `--no-reset` to create-only.

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

from app.db.client import connect_db, disconnect_db, get_db
from app.services.admin_bootstrap_service import (
    MIN_PASSWORD_LENGTH,
    AdminPasswordTooShortError,
    ensure_admin_user,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or refresh an Administrator account.")
    parser.add_argument("--username", required=True, help="Administrator username.")
    parser.add_argument(
        "--password",
        default=None,
        help="Administrator password. Defaults to the ADMIN_PASSWORD environment variable.",
    )
    parser.add_argument("--role", default="admin", help="Role stored on the account.")
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Leave the password untouched if the account already exists.",
    )
    return parser.parse_args(argv)


async def seed_admin(
    *,
    username: str,
    password: str,
    role: str = "admin",
    reset_existing: bool = True,
) -> str:
    """Connect, provision `username`, and disconnect; returns the outcome."""
    await connect_db()
    try:
        return await ensure_admin_user(
            get_db(),
            username=username,
            password=password,
            role=role,
            reset_existing=reset_existing,
        )
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

    try:
        outcome = asyncio.run(
            seed_admin(
                username=args.username,
                password=password,
                role=args.role,
                reset_existing=not args.no_reset,
            )
        )
    except AdminPasswordTooShortError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"Administrator '{args.username}': {outcome}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
