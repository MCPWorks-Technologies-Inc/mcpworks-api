"""OAuth service - account creation and linking logic for social login."""

import asyncio
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.config import get_settings
from mcpworks_api.core.security import create_access_token, create_refresh_token
from mcpworks_api.models import Account, AuditLog, OAuthAccount, User

logger = structlog.get_logger(__name__)


class OAuthService:
    """Handles OAuth account creation, linking, and JWT issuance."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_or_create_user_from_oauth(
        self,
        provider: str,
        provider_user_id: str,
        email: str,
        name: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[User, str, str, int, bool]:
        """Find or create a user from OAuth provider data.

        Matching order:
        1. Existing OAuthAccount with same provider + provider_user_id → return user
        2. Existing User with same email → link OAuth identity, return user
        3. No match → create new User + OAuthAccount

        Returns:
            Tuple of (user, access_token, refresh_token, expires_in, is_new_user)
        """
        settings = get_settings()
        is_new_user = False

        result = await self.db.execute(
            select(OAuthAccount).where(
                OAuthAccount.provider == provider,
                OAuthAccount.provider_user_id == provider_user_id,
            )
        )
        existing_oauth = result.scalar_one_or_none()

        if existing_oauth:
            user_result = await self.db.execute(
                select(User).where(User.id == existing_oauth.user_id)
            )
            user = user_result.scalar_one()
            if user.status in ("pending_approval", "pending_verification"):
                user.status = "active"
                user.email_verified = True
                await self._log_oauth_event(
                    user.id, "oauth_auto_approved", provider, ip_address, user_agent
                )
            await self._log_oauth_event(user.id, "oauth_login", provider, ip_address, user_agent)
        else:
            user_result = await self.db.execute(select(User).where(User.email == email.lower()))
            user = user_result.scalar_one_or_none()

            if user:
                if user.status in ("pending_approval", "pending_verification"):
                    user.status = "active"
                    user.email_verified = True
                oauth_account = OAuthAccount(
                    user_id=user.id,
                    provider=provider,
                    provider_user_id=provider_user_id,
                    provider_email=email,
                )
                self.db.add(oauth_account)
                await self._log_oauth_event(
                    user.id, "oauth_linked", provider, ip_address, user_agent
                )
            else:
                user = User(
                    email=email.lower(),
                    password_hash=None,
                    name=name,
                    tier="trial-agent",
                    status="active",
                    email_verified=True,
                )
                self.db.add(user)
                await self.db.flush()

                account = Account(
                    user_id=user.id,
                    name=name or email.split("@")[0],
                )
                self.db.add(account)

                oauth_account = OAuthAccount(
                    user_id=user.id,
                    provider=provider,
                    provider_user_id=provider_user_id,
                    provider_email=email,
                )
                self.db.add(oauth_account)
                is_new_user = True
                await self._log_oauth_event(
                    user.id, "oauth_registered", provider, ip_address, user_agent
                )

        if user.status not in ("active",) and not is_new_user:
            from mcpworks_api.services.auth import InvalidCredentialsError

            raise InvalidCredentialsError(message=f"Account is {user.status}")

        access_token = create_access_token(
            user_id=str(user.id),
            scopes=["read", "write", "execute"],
            additional_claims={
                "tier": user.tier,
                "email": user.email,
            },
        )
        refresh_token = create_refresh_token(user_id=str(user.id))
        expires_in = settings.jwt_access_token_expire_minutes * 60

        if is_new_user:
            asyncio.create_task(self._send_welcome_email(user.email, name))
            asyncio.create_task(
                self._send_registration_discord_alert(
                    user.email,
                    name,
                    ip_address,
                    user_agent,
                )
            )

        return user, access_token, refresh_token, expires_in, is_new_user

    async def _log_oauth_event(
        self,
        user_id: uuid.UUID,
        action: str,
        provider: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        audit_log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type="oauth",
            ip_address=ip_address,
            user_agent=user_agent,
            event_data={"provider": provider},
        )
        self.db.add(audit_log)

        asyncio.create_task(
            self._fire_oauth_security_event(action, provider, str(user_id), ip_address)
        )

    @staticmethod
    async def _send_welcome_email(email: str, name: str | None) -> None:
        try:
            from mcpworks_api.services.email import send_welcome_email

            await send_welcome_email(email, name)
        except Exception:
            logger.warning("welcome_email_failed", email=email)

    @staticmethod
    async def _send_registration_discord_alert(
        email: str, name: str | None, ip_address: str | None, user_agent: str | None
    ) -> None:
        try:
            from mcpworks_api.services.discord_alerts import send_new_account_alert

            await send_new_account_alert(email, name, ip_address, user_agent)
        except Exception:
            logger.warning("registration_discord_alert_failed", email=email)

    @staticmethod
    async def _fire_oauth_security_event(
        action: str,
        provider: str,
        actor_id: str,
        actor_ip: str | None,
    ) -> None:
        from mcpworks_api.core.database import get_db_context
        from mcpworks_api.services.security_event import fire_security_event

        async with get_db_context() as db:
            await fire_security_event(
                db,
                event_type=f"auth.{action}",
                severity="info",
                actor_ip=actor_ip,
                actor_id=actor_id,
                details={"provider": provider},
            )
