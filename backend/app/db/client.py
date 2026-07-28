"""Prisma client wrapper.

Owns the single Prisma client instance used by the whole backend process
(the MVP deliberately has no dedicated connection pooler — Requirement
9.19 / design.md -> Technology Stack and Constraints). Repositories (task
3.3+) depend on `get_db()` rather than importing `Prisma` directly, so
Prisma models never leak across the API boundary.

Timestamps: Prisma Client Python returns `datetime` values from `timestamptz`
columns as UTC-aware `datetime` objects; this module does not need to do any
conversion itself, but `utcnow()` is provided so callers construct new
timestamps consistently in UTC rather than local time.
"""

from __future__ import annotations

from datetime import UTC, datetime

from prisma import Prisma

_client: Prisma | None = None


def utcnow() -> datetime:
    """Return the current time as a UTC-aware datetime.

    Use this instead of `datetime.now()` anywhere the backend constructs a
    timestamp value, so every stored time is unambiguously UTC.
    """
    return datetime.now(UTC)


def get_db() -> Prisma:
    """Return the process-wide Prisma client, creating it on first access.

    Does not connect; call `connect_db()` / `disconnect_db()` around the
    application lifespan (see `app.main`).
    """
    global _client
    if _client is None:
        _client = Prisma()
    return _client


async def connect_db() -> None:
    """Open the single Prisma client connection for this process."""
    db = get_db()
    if not db.is_connected():
        await db.connect()


async def disconnect_db() -> None:
    """Close the single Prisma client connection for this process."""
    db = get_db()
    if db.is_connected():
        await db.disconnect()


# Alias for backward compatibility
get_prisma = get_db

__all__ = ["get_db", "get_prisma", "connect_db", "disconnect_db", "utcnow"]
