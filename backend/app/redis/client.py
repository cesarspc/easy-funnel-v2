"""Upstash Redis client module."""

from __future__ import annotations

from upstash_redis import AsyncRedis

from app.core.settings import Settings


class RedisClient:
    """Upstash Redis client wrapper."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._client: AsyncRedis | None = None

    async def get_client(self) -> AsyncRedis:
        """Get or create the Redis client."""
        if self._client is None:
            self._client = AsyncRedis(
                url=self._settings.upstash_redis_rest_url,
                token=self._settings.upstash_redis_rest_token,
            )
        return self._client

    async def ping(self) -> bool:
        """Ping Redis to verify connectivity."""
        client = await self.get_client()
        return await client.ping() == "PONG"


# Global client instance for dependency injection
_redis_client: RedisClient | None = None


def get_redis_client(settings: Settings | None = None) -> RedisClient:
    """Get or create the global Redis client."""
    global _redis_client
    if _redis_client is None:
        from app.core.settings import get_settings
        _redis_client = RedisClient(settings or get_settings())
    return _redis_client


async def get_redis() -> AsyncRedis:
    """Get the Redis client for dependency injection."""
    client = get_redis_client()
    return await client.get_client()
