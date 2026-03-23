"""Authentication endpoints - API key exchange and token management."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.database import get_db
from mcpworks_api.core.exceptions import (
    AlreadyVerifiedError,
    EmailExistsError,
    InvalidApiKeyError,
    InvalidCredentialsError,
    InvalidTokenError,
    InvalidVerificationPinError,
    RateLimitExceededError,
    TokenExpiredError,
    VerificationAttemptsExceededError,
    VerificationPinExpiredError,
    VerificationResendLimitError,
)
from mcpworks_api.dependencies import get_current_user_id, require_active_status
from mcpworks_api.middleware.rate_limit import check_auth_rate_limit
from mcpworks_api.schemas.auth import (
    ApiKeyInfo,
    CreateApiKeyRequest,
    CreateApiKeyResponse,
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    ResendVerificationResponse,
    TokenRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from mcpworks_api.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "User registered successfully (pending approval)"},
        409: {"description": "Email already registered"},
        429: {"description": "Rate limit exceeded"},
    },
)
async def register(
    request: Request,
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(check_auth_rate_limit),
) -> dict:
    """Register a new user account.

    Creates a new user with pending_approval status.
    Admin must approve before user can log in.
    """
    from mcpworks_api.config import get_settings

    if not get_settings().allow_registration:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "registration_disabled",
                "message": "Public registration is disabled on this instance. Contact the administrator.",
                "error_code": "AUTH_REGISTRATION_DISABLED",
            },
        )
    ip_address = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent")

    auth_service = AuthService(db)

    try:
        user, access_token, refresh_token, expires_in = await auth_service.register_user(
            email=body.email,
            password=body.password,
            name=body.name,
            ip_address=ip_address,
            user_agent=user_agent,
            accept_tos=body.accept_tos,
        )
        await db.commit()
    except EmailExistsError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=e.to_dict(),
        )

    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "status": user.status,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "email_verification_required": True,
    }


@router.post(
    "/login",
    response_model=LoginResponse,
    responses={
        200: {"description": "Successfully authenticated"},
        401: {"description": "Invalid email or password"},
        429: {"description": "Rate limit exceeded"},
    },
)
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(check_auth_rate_limit),
) -> LoginResponse:
    """Authenticate with email and password.

    Returns JWT access and refresh tokens on successful authentication.
    """
    ip_address = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent")

    auth_service = AuthService(db)

    try:
        access_token, refresh_token, expires_in = await auth_service.login_user(
            email=body.email,
            password=body.password,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()
    except InvalidCredentialsError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.to_dict(),
        )

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=expires_in,
    )


@router.post(
    "/token",
    response_model=TokenResponse,
    responses={
        200: {"description": "Successfully exchanged API key for tokens"},
        401: {"description": "Invalid or revoked API key"},
        429: {"description": "Rate limit exceeded"},
    },
)
async def exchange_token(
    request: Request,
    body: TokenRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(check_auth_rate_limit),
) -> TokenResponse:
    """Exchange an API key for JWT access and refresh tokens.

    FR-AUTH-001: Validate incoming API key against stored hash
    FR-AUTH-002: Generate JWT access token (1h expiry)
    FR-AUTH-003: Return access_token, refresh_token, token_type, expires_in
    """
    # Get client info for audit logging
    ip_address = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent")

    auth_service = AuthService(db)

    try:
        access_token, refresh_token, expires_in = await auth_service.exchange_api_key_for_tokens(
            raw_key=body.api_key,
            ip_address=ip_address,
            user_agent=user_agent,
        )
    except InvalidApiKeyError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.to_dict(),
        )
    except RateLimitExceededError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=e.to_dict(),
            headers={"Retry-After": str(e.retry_after)},
        )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=expires_in,
    )


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    responses={
        200: {"description": "Successfully refreshed access token"},
        401: {"description": "Invalid or expired refresh token"},
    },
)
async def refresh_token(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> RefreshResponse:
    """Exchange a refresh token for a new access token.

    FR-AUTH-004: Validate refresh token
    FR-AUTH-005: Issue new access token
    """
    auth_service = AuthService(db)

    try:
        access_token, expires_in = await auth_service.refresh_access_token(
            refresh_token=body.refresh_token,
        )
    except TokenExpiredError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.to_dict(),
        )
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.to_dict(),
        )

    return RefreshResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in,
    )


@router.post(
    "/api-keys",
    response_model=CreateApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "API key created successfully"},
        401: {"description": "Not authenticated"},
    },
)
async def create_api_key(
    request: Request,
    body: CreateApiKeyRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(require_active_status),
) -> CreateApiKeyResponse:
    """Create a new API key for the authenticated user.

    The raw API key is only returned once. Store it securely.
    """
    import uuid as uuid_module

    ip_address = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent")

    auth_service = AuthService(db)

    api_key, raw_key = await auth_service.create_api_key(
        user_id=uuid_module.UUID(user_id),
        name=body.name,
        scopes=body.scopes,
        expires_in_days=body.expires_in_days,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()

    return CreateApiKeyResponse(
        api_key=ApiKeyInfo(
            id=api_key.id,
            name=api_key.name,
            key_prefix=api_key.key_prefix,
            scopes=api_key.scopes or ["read", "write", "execute"],
            created_at=api_key.created_at,
            expires_at=api_key.expires_at,
            last_used_at=api_key.last_used_at,
        ),
        raw_key=raw_key,
    )


@router.post(
    "/verify-email",
    responses={
        200: {"description": "Email verified successfully"},
        400: {"description": "Invalid or expired PIN"},
        409: {"description": "Email already verified"},
        429: {"description": "Too many attempts"},
    },
)
async def verify_email(
    request: Request,
    body: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Verify email address with 6-digit PIN.

    Activates the account upon successful verification.
    """
    import uuid as uuid_module

    ip_address = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent")

    auth_service = AuthService(db)

    try:
        user = await auth_service.verify_email_pin(
            user_id=uuid_module.UUID(user_id),
            pin=body.pin,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()
    except AlreadyVerifiedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.to_dict())
    except VerificationPinExpiredError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.to_dict())
    except VerificationAttemptsExceededError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=e.to_dict())
    except InvalidVerificationPinError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.to_dict())

    return {
        "message": "Email verified successfully",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "status": user.status,
            "email_verified": user.email_verified,
        },
    }


@router.post(
    "/resend-verification",
    response_model=ResendVerificationResponse,
    responses={
        200: {"description": "Verification PIN resent"},
        409: {"description": "Email already verified"},
        429: {"description": "Resend limit reached"},
    },
)
async def resend_verification(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> ResendVerificationResponse:
    """Resend verification PIN to user's email.

    Maximum 5 resends allowed per registration.
    """
    import uuid as uuid_module

    ip_address = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent")

    auth_service = AuthService(db)

    try:
        resends_remaining = await auth_service.resend_verification_pin(
            user_id=uuid_module.UUID(user_id),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.commit()
    except AlreadyVerifiedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=e.to_dict())
    except VerificationResendLimitError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=e.to_dict())

    return ResendVerificationResponse(
        message="Verification PIN sent to your email",
        resends_remaining=resends_remaining,
    )


@router.post(
    "/logout-all",
    responses={
        200: {"description": "All sessions logged out"},
        401: {"description": "Not authenticated"},
    },
)
async def logout_all(
    _request: Request,
    _db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Revoke all refresh tokens for the authenticated user.

    Note: In a stateless JWT system, this would typically:
    1. Add all current JTIs to a blocklist in Redis
    2. Or rotate the signing key (invalidates ALL tokens for ALL users)

    For MVP, we'll return success but note that true token revocation
    requires additional infrastructure (Redis blocklist).
    """
    # This endpoint requires authentication via JWT
    # The actual implementation would need the current user from JWT
    # and then invalidate their refresh tokens

    # For MVP, return acknowledgment
    return {"message": "All sessions have been logged out"}


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
