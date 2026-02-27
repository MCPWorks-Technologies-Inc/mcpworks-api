"""OAuth endpoints - social login via Google and GitHub."""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.config import get_settings
from mcpworks_api.core.database import get_db
from mcpworks_api.middleware.rate_limit import check_auth_rate_limit
from mcpworks_api.services.oauth import OAuthService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth/oauth", tags=["authentication"])

VALID_PROVIDERS = {"google", "github"}


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    if request.client:
        return request.client.host
    return "unknown"


@router.get("/{provider}/login")
async def oauth_login(
    provider: str,
    request: Request,
    _: None = Depends(check_auth_rate_limit),
) -> RedirectResponse:
    """Initiate OAuth login flow — redirects to provider consent screen."""
    if provider not in VALID_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "INVALID_PROVIDER", "message": f"Invalid provider: {provider}"},
        )

    oauth = request.app.state.oauth
    client = oauth.create_client(provider)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "PROVIDER_NOT_CONFIGURED",
                "message": f"{provider} OAuth is not configured",
            },
        )

    settings = get_settings()
    base_url = settings.jwt_issuer
    redirect_uri = f"{base_url}/v1/auth/oauth/{provider}/callback"

    return await client.authorize_redirect(request, redirect_uri)


@router.get("/{provider}/callback")
async def oauth_callback(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(check_auth_rate_limit),
) -> dict:
    """Handle OAuth provider callback — exchange code for JWT."""
    if provider not in VALID_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "INVALID_PROVIDER", "message": f"Invalid provider: {provider}"},
        )

    oauth = request.app.state.oauth
    client = oauth.create_client(provider)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "PROVIDER_NOT_CONFIGURED",
                "message": f"{provider} OAuth is not configured",
            },
        )

    try:
        token = await client.authorize_access_token(request)
    except Exception as e:
        logger.warning("oauth_callback_failed", provider=provider, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "OAUTH_FAILED", "message": "OAuth authorization failed"},
        )

    email, name, provider_user_id = await _extract_user_info(client, token, provider)

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "EMAIL_REQUIRED", "message": "Could not retrieve email from provider"},
        )

    ip_address = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent")

    oauth_service = OAuthService(db)
    (
        user,
        access_token,
        refresh_token,
        expires_in,
        is_new_user,
    ) = await oauth_service.get_or_create_user_from_oauth(
        provider=provider,
        provider_user_id=provider_user_id,
        email=email,
        name=name,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "is_new_user": is_new_user,
    }


async def _extract_user_info(
    client: object, token: dict, provider: str
) -> tuple[str | None, str | None, str]:
    """Extract email, name, and provider_user_id from OAuth token/userinfo."""
    if provider == "google":
        userinfo = token.get("userinfo", {})
        return (
            userinfo.get("email"),
            userinfo.get("name"),
            userinfo.get("sub", ""),
        )

    if provider == "github":
        resp = await client.get("user", token=token)
        user_data = resp.json()
        provider_user_id = str(user_data.get("id", ""))
        email = user_data.get("email")
        name = user_data.get("name")

        if not email:
            emails_resp = await client.get("user/emails", token=token)
            emails = emails_resp.json()
            for entry in emails:
                if entry.get("primary") and entry.get("verified"):
                    email = entry["email"]
                    break

        return email, name, provider_user_id

    return None, None, ""
