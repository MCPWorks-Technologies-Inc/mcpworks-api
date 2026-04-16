"""Function result caching via Redis."""

import hashlib
import json

import structlog

from mcpworks_api.core.redis import get_redis_context

logger = structlog.get_logger(__name__)


def make_cache_key(function_id: str, version: int, input_data: dict | None) -> str:
    canonical = json.dumps(input_data or {}, sort_keys=True, separators=(",", ":"))
    input_hash = hashlib.sha256(canonical.encode()).hexdigest()[:16]
    return f"fncache:{function_id}:v{version}:{input_hash}"


def get_cache_policy(function) -> tuple[bool, int]:
    policy = getattr(function, "cache_policy", None)
    if not policy or not isinstance(policy, dict):
        return False, 0
    enabled = policy.get("enabled", False)
    ttl = policy.get("ttl_seconds", 300)
    if not enabled or ttl <= 0:
        return False, 0
    return True, ttl


async def get_cached_result(cache_key: str) -> dict | None:
    try:
        async with get_redis_context() as redis:
            raw = await redis.get(cache_key)
            if raw is None:
                return None
            return json.loads(raw)
    except Exception:
        logger.warning("result_cache_get_error", cache_key=cache_key)
        return None


async def set_cached_result(cache_key: str, result_output, ttl_seconds: int) -> None:
    try:
        value = json.dumps(result_output)
        async with get_redis_context() as redis:
            await redis.set(cache_key, value, ex=ttl_seconds)
    except Exception:
        logger.warning("result_cache_set_error", cache_key=cache_key)
