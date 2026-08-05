"""Administrator account bootstrap (Requirement 7.1, 7.2, 10.10).

The platform has no self-service signup, so the first Administrator must be
provisioned out of band. This module is the single implementation of that
provisioning, used by two callers:

- `app.main` on application startup, driven by `ADMIN_USERNAME` /
  `ADMIN_PASSWORD`, so a fresh deployment is reachable without a manual
  one-off task.
- `scripts.seed_admin` for local/maintenance use from a shell.

Connection lifecycle is the caller's responsibility: this module assumes an
already-connected Prisma client so it can run inside the FastAPI lifespan
without closing the process-wide connection.

The password is only ever persisted as an Argon2id hash, and every mutation
is recorded in `audit_log` like any other administrative change.
"""

from __future__ import annotations

from typing import Literal

from prisma import Prisma

from app.core.password_hashing import hash_password

#: Minimum accepted password length. Enforced here rather than only in the CLI
#: so an under-length `ADMIN_PASSWORD` cannot silently provision a weak
#: Administrator on a deployed environment.
MIN_PASSWORD_LENGTH = 12

BootstrapOutcome = Literal["created", "password_reset", "unchanged"]


class AdminPasswordTooShortError(ValueError):
    """Raised when the supplied password is below `MIN_PASSWORD_LENGTH`."""


async def ensure_admin_user(
    db: Prisma,
    *,
    username: str,
    password: str,
    role: str = "admin",
    reset_existing: bool = False,
) -> BootstrapOutcome:
    """Provision `username`, returning what was actually changed.

    Outcomes:
    - `"created"`: the account did not exist and was created.
    - `"password_reset"`: the account existed and `reset_existing` was true,
      so the stored hash was replaced.
    - `"unchanged"`: the account existed and `reset_existing` was false.

    Defaulting `reset_existing` to false keeps restarts idempotent *and*
    non-destructive: a container reboot must not silently roll a live
    Administrator's credentials back to whatever value the environment
    variable happens to hold.

    Raises:
        AdminPasswordTooShortError: if `password` is shorter than
            `MIN_PASSWORD_LENGTH`.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AdminPasswordTooShortError(
            f"Administrator password must be at least {MIN_PASSWORD_LENGTH} characters."
        )

    existing = await db.adminuser.find_unique(where={"username": username})

    if existing is not None and not reset_existing:
        return "unchanged"

    # Hash only once a write is actually going to happen — Argon2id is
    # deliberately expensive, and the common case (existing account, no reset)
    # should not pay for it on every boot.
    password_hash = hash_password(password)

    if existing is None:
        await db.adminuser.create(
            data={"username": username, "passwordHash": password_hash, "role": role}
        )
        outcome: BootstrapOutcome = "created"
    else:
        await db.adminuser.update(
            where={"username": username},
            data={"passwordHash": password_hash, "role": role},
        )
        outcome = "password_reset"

    await db.auditlog.create(
        data={
            "actor": "admin_bootstrap",
            "action": f"admin_user.{outcome}",
            "targetType": "admin_user",
            "targetId": username,
            "result": "success",
        }
    )
    return outcome
