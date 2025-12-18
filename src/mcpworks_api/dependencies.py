"""FastAPI dependency providers for common resources."""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.database import get_db
from mcpworks_api.core.exceptions import InvalidTokenError, TokenExpiredError
from mcpworks_api.core.redis import get_redis
from mcpworks_api.core.security import verify_access_token

# Type aliases for cleaner dependency injection
DBSession = Annotated[AsyncSession, Depends(get_db)]
RedisClient = Annotated[Redis, Depends(get_redis)]


async def get_current_user_id(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Extract and validate user ID from JWT token in Authorization header.

    Args:
        authorization: Authorization header value (Bearer <token>)

    Returns:
        User ID from validated token

    Raises:
        HTTPException: If no token provided or token is invalid
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "MISSING_TOKEN", "message": "Authorization header required"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract token from "Bearer <token>" format
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "INVALID_TOKEN_FORMAT", "message": "Expected 'Bearer <token>'"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]

    try:
        payload = verify_access_token(token)
        user_id: str = payload["sub"]
        return user_id
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "TOKEN_EXPIRED", "message": "Access token has expired"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "INVALID_TOKEN", "message": str(e)},
            headers={"WWW-Authenticate": "Bearer"},
        )


# Type alias for authenticated user ID
CurrentUserId = Annotated[str, Depends(get_current_user_id)]


async def get_optional_user_id(
    authorization: Annotated[str | None, Header()] = None,
) -> str | None:
    """Extract user ID from JWT token if present, otherwise return None.

    Useful for endpoints that work both authenticated and anonymously.

    Args:
        authorization: Authorization header value (Bearer <token>)

    Returns:
        User ID if valid token provided, None otherwise
    """
    if not authorization:
        return None

    try:
        return await get_current_user_id(authorization)
    except HTTPException:
        return None


# Type alias for optional authenticated user ID
OptionalUserId = Annotated[str | None, Depends(get_optional_user_id)]


def require_scope(required_scope: str) -> Callable[..., Awaitable[None]]:
    """Dependency factory that requires a specific scope in the JWT.

    Usage:
        @router.post("/admin/users")
        async def admin_endpoint(
            user_id: CurrentUserId,
            _: Annotated[None, Depends(require_scope("admin"))]
        ):
            ...

    Args:
        required_scope: The scope that must be present in the token

    Returns:
        Dependency function that validates the scope
    """

    async def check_scope(
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "MISSING_TOKEN", "message": "Authorization header required"},
            )

        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "INVALID_TOKEN_FORMAT", "message": "Expected 'Bearer <token>'"},
            )

        token = parts[1]

        try:
            payload = verify_access_token(token)
            scopes = payload.get("scopes", [])
            if required_scope not in scopes:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": "INSUFFICIENT_SCOPE",
                        "message": f"Scope '{required_scope}' required",
                    },
                )
        except TokenExpiredError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "TOKEN_EXPIRED", "message": "Access token has expired"},
            )
        except InvalidTokenError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "INVALID_TOKEN", "message": str(e)},
            )

    return check_scope


async def verify_agent_callback_secret(
    x_agent_secret: Annotated[str | None, Header()] = None,
) -> None:
    """Verify the shared secret for agent callback authentication.

    The mcpworks-agent service must include the X-Agent-Secret header
    when calling callback endpoints.

    Raises:
        HTTPException: If secret is missing or invalid.
    """
    from mcpworks_api.config import get_settings

    settings = get_settings()

    # In development (no secret configured), allow requests
    if not settings.agent_callback_secret:
        return

    if not x_agent_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "MISSING_SECRET",
                "message": "X-Agent-Secret header required",
            },
        )

    # Use constant-time comparison to prevent timing attacks
    import hmac

    if not hmac.compare_digest(x_agent_secret, settings.agent_callback_secret):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "INVALID_SECRET",
                "message": "Invalid agent callback secret",
            },
        )
