"""Async Redis connection management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from redis.asyncio import ConnectionPool, Redis

from mcpworks_api.config import get_settings

# Connection pool
_pool: ConnectionPool | None = None


async def get_redis_pool() -> ConnectionPool:
    """Get or create Redis connection pool."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(
            get_settings().redis_url,
            max_connections=10,
            decode_responses=True,
        )
    return _pool


async def get_redis() -> AsyncGenerator[Redis, None]:
    """Dependency that provides a Redis client.

    Usage:
        @app.get("/rate-limit")
        async def check_rate(redis: Redis = Depends(get_redis)):
            ...
    """
    pool = await get_redis_pool()
    client = Redis(connection_pool=pool)
    try:
        yield client
    finally:
        await client.aclose()  # type: ignore[attr-defined]


@asynccontextmanager
async def get_redis_context() -> AsyncGenerator[Redis, None]:
    """Context manager for Redis client outside of request context.

    Usage:
        async with get_redis_context() as redis:
            await redis.set("key", "value")
    """
    pool = await get_redis_pool()
    client = Redis(connection_pool=pool)
    try:
        yield client
    finally:
        await client.aclose()  # type: ignore[attr-defined]


async def init_redis() -> None:
    """Initialize Redis connection pool and test connection."""
    pool = await get_redis_pool()
    client = Redis(connection_pool=pool)
    try:
        await client.ping()
    finally:
        await client.aclose()  # type: ignore[attr-defined]


async def close_redis() -> None:
    """Close Redis connection pool."""
    global _pool
    if _pool is not None:
        await _pool.disconnect()
        _pool = None


class RateLimiter:
    """Redis-based sliding window rate limiter."""

    def __init__(self, redis_client: Redis) -> None:
        self.redis = redis_client

    async def is_rate_limited(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> tuple[bool, int]:
        """Check if request should be rate limited.

        Args:
            key: Unique identifier (e.g., "auth_fail:192.168.1.1")
            limit: Maximum requests allowed in window
            window_seconds: Time window in seconds

        Returns:
            Tuple of (is_limited, current_count)
        """
        # Use sliding window counter pattern
        current = await self.redis.incr(key)

        if current == 1:
            # First request, set expiry
            await self.redis.expire(key, window_seconds)

        return current > limit, current

    async def get_remaining(self, key: str, limit: int) -> int:
        """Get remaining requests before rate limit."""
        current = await self.redis.get(key)
        if current is None:
            return limit
        return max(0, limit - int(current))

    async def reset(self, key: str) -> None:
        """Reset rate limit counter for key."""
        await self.redis.delete(key)
