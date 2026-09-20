"""Vendor-neutral asynchronous Redis client."""

from __future__ import annotations

from redis.asyncio import Redis

from app.core.settings import Settings


class ApplicationRedis(Redis):
    """redis-py client accepting the application's explicit keys/args form."""

    async def eval(  # type: ignore[override]
        self,
        script: str,
        numkeys: int | None = None,
        *keys_and_args: str,
        keys: list[str] | None = None,
        args: list[str] | None = None,
    ):
        if keys is not None:
            return await super().eval(script, len(keys), *keys, *(args or []))
        return await super().eval(script, numkeys or 0, *keys_and_args)


class RedisClient:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client: ApplicationRedis | None = None

    async def get_client(self) -> ApplicationRedis:
        if self._client is None:
            self._client = ApplicationRedis.from_url(
                self._settings.redis_url,
                decode_responses=True,
            )
        return self._client

    async def ping(self) -> bool:
        return bool(await (await self.get_client()).ping())


_redis_client: RedisClient | None = None


def get_redis_client(settings: Settings | None = None) -> RedisClient:
    global _redis_client
    if _redis_client is None:
        from app.core.settings import get_settings

        _redis_client = RedisClient(settings or get_settings())
    return _redis_client


async def get_redis() -> Redis:
    return await get_redis_client().get_client()
