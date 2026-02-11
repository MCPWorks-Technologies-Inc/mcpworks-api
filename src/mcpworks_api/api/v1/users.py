"""User endpoints - profile and account management."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.database import get_db
from mcpworks_api.core.exceptions import ApiKeyNotFoundError, UserNotFoundError
from mcpworks_api.dependencies import CurrentUserId
from mcpworks_api.models import User
from mcpworks_api.schemas.user import (
    ApiKeyCreated,
    ApiKeyList,
    ApiKeySummary,
    CreateApiKeyRequest,
    UserProfile,
)
from mcpworks_api.services.auth import AuthService

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/me",
    response_model=UserProfile,
    responses={
        200: {"description": "Current user profile"},
        401: {"description": "Not authenticated or token expired"},
    },
)
async def get_current_user(
    user_id: CurrentUserId,
    db: AsyncSession = Depends(get_db),
) -> UserProfile:
    """Get the authenticated user's profile.

    Requires valid JWT access token in Authorization header.
    """
    # Fetch user
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "USER_NOT_FOUND",
                "message": "User not found",
            },
        )

    return UserProfile(
        id=user.id,
        email=user.email,
        name=user.name,
        tier=user.tier,
        status=user.status,
        email_verified=user.email_verified,
        created_at=user.created_at,
    )


@router.post(
    "/me/api-keys",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "API key created successfully"},
        401: {"description": "Not authenticated or token expired"},
    },
)
async def create_api_key(
    request: Request,
    body: CreateApiKeyRequest,
    user_id: CurrentUserId,
    db: AsyncSession = Depends(get_db),
) -> ApiKeyCreated:
    """Create a new API key for the authenticated user.

    The full API key is returned only once. Store it securely.
    """
    ip_address = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent")

    auth_service = AuthService(db)

    try:
        api_key, raw_key = await auth_service.create_api_key(
            user_id=uuid.UUID(user_id),
            name=body.name,
            scopes=body.scopes,
            expires_in_days=body.expires_in_days,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()
    except UserNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.to_dict(),
        )

    return ApiKeyCreated(
        id=api_key.id,
        key=raw_key,
        key_prefix=api_key.key_prefix,
        name=api_key.name,
        scopes=api_key.scopes,
        created_at=api_key.created_at,
    )


@router.get(
    "/me/api-keys",
    response_model=ApiKeyList,
    responses={
        200: {"description": "List of API keys"},
        401: {"description": "Not authenticated or token expired"},
    },
)
async def list_api_keys(
    user_id: CurrentUserId,
    db: AsyncSession = Depends(get_db),
) -> ApiKeyList:
    """List all API keys for the authenticated user.

    Does not include revoked keys.
    """
    auth_service = AuthService(db)

    api_keys = await auth_service.list_api_keys(
        user_id=uuid.UUID(user_id),
        include_revoked=False,
    )

    items = [
        ApiKeySummary(
            id=key.id,
            key_prefix=key.key_prefix,
            name=key.name,
            scopes=key.scopes,
            created_at=key.created_at,
            last_used_at=key.last_used_at,
            expires_at=key.expires_at,
            is_revoked=key.is_revoked,
        )
        for key in api_keys
    ]

    return ApiKeyList(
        items=items,
        total=len(items),
    )


@router.delete(
    "/me/api-keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        204: {"description": "API key revoked successfully"},
        401: {"description": "Not authenticated or token expired"},
        404: {"description": "API key not found"},
    },
)
async def revoke_api_key(
    key_id: uuid.UUID,
    request: Request,
    user_id: CurrentUserId,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke an API key.

    The key will be immediately invalidated and cannot be used.
    """
    ip_address = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent")

    auth_service = AuthService(db)

    try:
        await auth_service.revoke_api_key(
            user_id=uuid.UUID(user_id),
            key_id=key_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()
    except ApiKeyNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.to_dict(),
        )


def _get_client_ip(request: Request) -> str:
    """Extract client IP from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    if request.client:
        return request.client.host

    return "unknown"
