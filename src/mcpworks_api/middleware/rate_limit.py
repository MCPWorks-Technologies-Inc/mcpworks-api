"""Rate limiting middleware using Redis sliding window."""

import asyncio

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from mcpworks_api.core.redis import RateLimiter, get_redis_context


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware for rate limiting requests.

    Uses Redis sliding window counter pattern.
    Different limits for different endpoint types.
    """

    # Rate limit configurations per endpoint pattern
    LIMITS = {
        # Auth endpoints - stricter limits to prevent brute force
        "auth_failure": {"limit": 5, "window": 60},  # 5 failures per minute per IP
        "auth_attempt": {"limit": 20, "window": 60},  # 20 attempts per minute per IP
        # General API - per user
        "user_request": {"limit": 1000, "window": 3600},  # 1000 per hour per user
        # Unauthenticated - per IP
        "ip_request": {"limit": 100, "window": 3600},  # 100 per hour per IP
    }

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process request with rate limiting."""
        # Skip rate limiting for health endpoints
        if request.url.path.startswith("/v1/health"):
            return await call_next(request)

        # Get client IP
        client_ip = self._get_client_ip(request)

        # Check if this is an auth endpoint
        if request.url.path.startswith("/v1/auth"):
            # Check auth attempt limit (overall attempts)
            is_limited, remaining = await self._check_auth_rate_limit(client_ip)
            if is_limited:
                return self._rate_limit_response(
                    limit=self.LIMITS["auth_attempt"]["limit"],
                    window="1 minute",
                    retry_after=60,
                )

            # Check auth failure limit (failed attempts only)
            if await self._check_auth_failure_limit(client_ip):
                return self._rate_limit_response(
                    limit=self.LIMITS["auth_failure"]["limit"],
                    window="1 minute",
                    retry_after=60,
                )

        # Process request
        response = await call_next(request)

        # Track auth failures for rate limiting
        if request.url.path == "/v1/auth/token" and response.status_code == 401:
            await self._record_auth_failure(client_ip)
            # ORDER-022: Log auth failure as security event
            asyncio.create_task(
                self._log_security_event(
                    "auth.login_failed",
                    "warning",
                    client_ip,
                )
            )

        return response

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request."""
        # Check for forwarded headers (behind proxy)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        # Check for real IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Fall back to client host
        if request.client:
            return request.client.host

        return "unknown"

    async def _check_auth_rate_limit(self, client_ip: str) -> tuple[bool, int]:
        """Check if client has exceeded auth rate limit.

        Args:
            client_ip: Client IP address

        Returns:
            Tuple of (is_limited, remaining_requests)
        """
        config = self.LIMITS["auth_attempt"]
        key = f"ratelimit:auth:{client_ip}"

        async with get_redis_context() as redis:
            limiter = RateLimiter(redis)
            is_limited, current = await limiter.is_rate_limited(
                key, config["limit"], config["window"]
            )
            remaining = max(0, config["limit"] - current)

        return is_limited, remaining

    async def _record_auth_failure(self, client_ip: str) -> None:
        """Record an auth failure for rate limiting."""
        config = self.LIMITS["auth_failure"]
        key = f"ratelimit:auth_fail:{client_ip}"

        async with get_redis_context() as redis:
            limiter = RateLimiter(redis)
            await limiter.is_rate_limited(key, config["limit"], config["window"])

    async def _check_auth_failure_limit(self, client_ip: str) -> bool:
        """Check if client has exceeded auth failure limit.

        Uses check_rate_limited to read without incrementing the counter.
        Failures are only recorded via _record_auth_failure on actual 401 responses.

        Returns:
            True if rate limited, False otherwise
        """
        config = self.LIMITS["auth_failure"]
        key = f"ratelimit:auth_fail:{client_ip}"

        async with get_redis_context() as redis:
            limiter = RateLimiter(redis)
            is_limited, _ = await limiter.check_rate_limited(key, config["limit"])

        return is_limited

    @staticmethod
    async def _log_security_event(
        event_type: str,
        severity: str,
        actor_ip: str | None = None,
        actor_id: str | None = None,
        details: dict | None = None,
    ) -> None:
        """ORDER-022: Fire-and-forget security event logging."""
        from mcpworks_api.core.database import get_db_context
        from mcpworks_api.services.security_event import fire_security_event

        async with get_db_context() as db:
            await fire_security_event(
                db,
                event_type,
                severity,
                actor_ip=actor_ip,
                actor_id=actor_id,
                details=details,
            )

    def _rate_limit_response(self, limit: int, window: str, retry_after: int) -> JSONResponse:
        """Create rate limit exceeded response."""
        return JSONResponse(
            status_code=429,
            content={
                "error": "RATE_LIMIT_EXCEEDED",
                "message": f"Rate limit exceeded: {limit} requests per {window}",
                "details": {
                    "limit": limit,
                    "window": window,
                    "retry_after": retry_after,
                },
            },
            headers={"Retry-After": str(retry_after)},
        )


async def check_auth_rate_limit(request: Request) -> None:
    """Dependency to check auth rate limit before processing.

    This can be used as a FastAPI dependency on specific endpoints
    for more granular control.

    Uses check_rate_limited to read without incrementing the counter.
    Failures are only recorded by the middleware on actual 401 responses.

    Raises:
        RateLimitExceededError if rate limited
    """
    from mcpworks_api.core.exceptions import RateLimitExceededError

    # Get client IP
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    elif request.client:
        client_ip = request.client.host
    else:
        client_ip = "unknown"

    # Check failure limit (without incrementing)
    config = RateLimitMiddleware.LIMITS["auth_failure"]
    key = f"ratelimit:auth_fail:{client_ip}"

    async with get_redis_context() as redis:
        limiter = RateLimiter(redis)
        is_limited, _ = await limiter.check_rate_limited(key, config["limit"])

    if is_limited:
        raise RateLimitExceededError(
            limit=config["limit"],
            window="1 minute",
            retry_after=60,
        )
