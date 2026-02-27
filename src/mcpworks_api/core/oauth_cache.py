"""Redis-backed OAuth state cache for Authlib CSRF protection."""

from typing import Any

from mcpworks_api.core.redis import get_redis_context

OAUTH_STATE_TTL = 600


class RedisOAuthCache:
    """Authlib-compatible cache adapter backed by Redis.

    Authlib's OAuth client expects a cache with get/set/delete methods.
    This adapter stores OAuth state parameters (CSRF tokens) in Redis
    with a 10-minute TTL.
    """

    def __init__(self, prefix: str = "oauth_state:") -> None:
        self._prefix = prefix

    async def get(self, key: str) -> Any:
        async with get_redis_context() as redis:
            import json

            val = await redis.get(f"{self._prefix}{key}")
            if val is None:
                return None
            return json.loads(val)

    async def set(self, key: str, value: Any, expires: int | None = None) -> None:
        async with get_redis_context() as redis:
            import json

            ttl = expires or OAUTH_STATE_TTL
            await redis.set(f"{self._prefix}{key}", json.dumps(value), ex=ttl)

    async def delete(self, key: str) -> None:
        async with get_redis_context() as redis:
            await redis.delete(f"{self._prefix}{key}")
