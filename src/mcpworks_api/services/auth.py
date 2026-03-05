"""Authentication service - API key validation and JWT token management."""

import asyncio
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.config import get_settings
from mcpworks_api.core.exceptions import (
    AlreadyVerifiedError,
    ApiKeyNotFoundError,
    EmailExistsError,
    ForbiddenError,
    InvalidApiKeyError,
    InvalidCredentialsError,
    InvalidTokenError,
    InvalidVerificationPinError,
    NotFoundError,
    UserNotFoundError,
    VerificationAttemptsExceededError,
    VerificationPinExpiredError,
    VerificationResendLimitError,
)
from mcpworks_api.core.security import (
    check_needs_rehash,
    create_access_token,
    create_refresh_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_api_key,
    verify_password,
    verify_refresh_token,
)
from mcpworks_api.models import Account, APIKey, AuditAction, AuditLog, User

logger = structlog.get_logger(__name__)


class AuthService:
    """Service for authentication operations."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize auth service with database session."""
        self.db = db

    async def validate_api_key(
        self,
        raw_key: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> User:
        """Validate an API key and return the associated user.

        Args:
            raw_key: The raw API key string (e.g., "mcpw_a1b2c3...")
            ip_address: Client IP address for audit logging
            user_agent: Client user agent for audit logging

        Returns:
            The User associated with the valid API key

        Raises:
            InvalidApiKeyError: If the key is invalid, revoked, or expired
        """
        # Extract prefix for lookup (first 12 chars)
        if len(raw_key) < 12:
            await self._log_auth_failure(None, ip_address, user_agent, "Key too short")
            raise InvalidApiKeyError()

        key_prefix = raw_key[:12]

        # Find all keys with matching prefix
        result = await self.db.execute(
            select(APIKey)
            .where(APIKey.key_prefix == key_prefix)
            .where(APIKey.revoked_at.is_(None))  # Not revoked
        )
        api_keys = result.scalars().all()

        if not api_keys:
            await self._log_auth_failure(None, ip_address, user_agent, "No matching key prefix")
            raise InvalidApiKeyError()

        # Verify against each matching key's hash
        valid_key: APIKey | None = None
        for api_key in api_keys:
            if verify_api_key(raw_key, api_key.key_hash):
                valid_key = api_key
                break

        if not valid_key:
            await self._log_auth_failure(None, ip_address, user_agent, "Hash verification failed")
            raise InvalidApiKeyError()

        # Check if expired
        if valid_key.expires_at is not None and datetime.now(UTC) >= valid_key.expires_at:
            await self._log_auth_failure(valid_key.user_id, ip_address, user_agent, "Key expired")
            raise InvalidApiKeyError(message="API key has expired")

        # Check if hash needs rehash (parameters changed)
        if check_needs_rehash(valid_key.key_hash):
            # Update hash with new parameters
            valid_key.key_hash = hash_api_key(raw_key)

        # Update last used timestamp
        valid_key.last_used_at = datetime.now(UTC)

        # Fetch user
        result = await self.db.execute(select(User).where(User.id == valid_key.user_id))
        user = result.scalar_one_or_none()

        if not user or user.status != "active":
            await self._log_auth_failure(valid_key.user_id, ip_address, user_agent, "User inactive")
            raise InvalidApiKeyError(message="User account is not active")

        # Log successful auth
        await self._log_auth_success(user.id, valid_key.id, ip_address, user_agent)

        return user

    async def exchange_api_key_for_tokens(
        self,
        raw_key: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[str, str, int]:
        """Exchange an API key for JWT access and refresh tokens.

        Args:
            raw_key: The raw API key string
            ip_address: Client IP address for audit logging
            user_agent: Client user agent for audit logging

        Returns:
            Tuple of (access_token, refresh_token, expires_in_seconds)

        Raises:
            InvalidApiKeyError: If the key is invalid
        """
        user = await self.validate_api_key(raw_key, ip_address, user_agent)

        # Get scopes from the API key
        result = await self.db.execute(
            select(APIKey).where(APIKey.user_id == user.id).where(APIKey.key_prefix == raw_key[:12])
        )
        api_key = result.scalar_one()
        scopes = api_key.scopes or ["read", "write", "execute"]

        # Create tokens
        access_token = create_access_token(
            user_id=str(user.id),
            scopes=scopes,
            additional_claims={
                "tier": user.tier,
                "email": user.email,
            },
        )
        refresh_token = create_refresh_token(user_id=str(user.id))

        expires_in = get_settings().jwt_access_token_expire_minutes * 60

        return access_token, refresh_token, expires_in

    async def refresh_access_token(
        self,
        refresh_token: str,
    ) -> tuple[str, int]:
        """Exchange a refresh token for a new access token.

        Args:
            refresh_token: The JWT refresh token

        Returns:
            Tuple of (new_access_token, expires_in_seconds)

        Raises:
            InvalidTokenError: If the refresh token is invalid
        """
        # Verify refresh token
        payload = verify_refresh_token(refresh_token)
        user_id = payload["sub"]

        # Fetch user to get current tier and status
        result = await self.db.execute(select(User).where(User.id == uuid.UUID(user_id)))
        user = result.scalar_one_or_none()

        if not user or user.status != "active":
            raise InvalidTokenError(message="User account is not active")

        # Create new access token with current user data
        access_token = create_access_token(
            user_id=str(user.id),
            scopes=["read", "write", "execute"],  # Default scopes for refresh
            additional_claims={
                "tier": user.tier,
                "email": user.email,
            },
        )

        expires_in = get_settings().jwt_access_token_expire_minutes * 60

        return access_token, expires_in

    async def _log_auth_success(
        self,
        user_id: uuid.UUID,
        api_key_id: uuid.UUID,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        """Log successful authentication event."""
        audit_log = AuditLog(
            user_id=user_id,
            action=AuditAction.USER_LOGIN.value,
            resource_type="api_key",
            resource_id=api_key_id,
            ip_address=ip_address,
            user_agent=user_agent,
            event_data={"method": "api_key"},
        )
        self.db.add(audit_log)

    async def _log_auth_failure(
        self,
        user_id: uuid.UUID | None,
        ip_address: str | None,
        user_agent: str | None,
        reason: str,
    ) -> None:
        """Log failed authentication attempt."""
        audit_log = AuditLog(
            user_id=user_id,
            action=AuditAction.AUTH_FAILED.value,
            resource_type="api_key",
            ip_address=ip_address,
            user_agent=user_agent,
            event_data={"reason": reason},
        )
        self.db.add(audit_log)

        asyncio.create_task(
            self._fire_auth_security_event(
                ip_address,
                str(user_id) if user_id else None,
                reason,
            )
        )

    @staticmethod
    async def _fire_auth_security_event(
        actor_ip: str | None,
        actor_id: str | None,
        reason: str,
    ) -> None:
        """ORDER-022: Fire-and-forget security event for auth failures."""
        from mcpworks_api.core.database import get_db_context
        from mcpworks_api.services.security_event import fire_security_event

        async with get_db_context() as db:
            await fire_security_event(
                db,
                event_type="auth.login_failed",
                severity="warning",
                actor_ip=actor_ip,
                actor_id=actor_id,
                details={"reason": reason},
            )

    @staticmethod
    def _generate_pin() -> tuple[str, str]:
        """Generate a 6-digit PIN and its SHA-256 hash."""
        pin = f"{secrets.randbelow(1_000_000):06d}"
        pin_hash = hashlib.sha256(pin.encode()).hexdigest()
        return pin, pin_hash

    async def register_user(
        self,
        email: str,
        password: str,
        name: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        accept_tos: bool = False,
    ) -> tuple[User, str | None, str | None, int | None]:
        """Register a new user.

        Email/password registrations enter pending_verification status.
        A 6-digit PIN is emailed; account activates on verification.

        Args:
            email: User's email address.
            password: User's password (will be hashed).
            name: Optional display name.
            ip_address: Client IP address for audit logging.
            user_agent: Client user agent for audit logging.

        Returns:
            Tuple of (user, access_token, refresh_token, expires_in_seconds)

        Raises:
            EmailExistsError: If email is already registered.
        """
        result = await self.db.execute(select(User).where(User.email == email.lower()))
        existing = result.scalar_one_or_none()

        if existing:
            raise EmailExistsError()

        pin, pin_hash = self._generate_pin()

        user = User(
            email=email.lower(),
            password_hash=hash_password(password),
            name=name,
            tier="builder",
            status="pending_verification",
            email_verified=False,
            verification_token=pin_hash,
            verification_pin_expires_at=datetime.now(UTC) + timedelta(minutes=10),
            verification_attempts=0,
            verification_resend_count=0,
            tos_accepted_at=datetime.now(UTC) if accept_tos else None,
            tos_version="1.0.0" if accept_tos else None,
        )
        self.db.add(user)
        await self.db.flush()

        account = Account(
            user_id=user.id,
            name=name or email.split("@")[0],
        )
        self.db.add(account)

        audit_log = AuditLog(
            user_id=user.id,
            action=AuditAction.USER_REGISTERED.value,
            resource_type="user",
            resource_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            event_data={"email": user.email, "status": "pending_verification"},
        )
        self.db.add(audit_log)

        asyncio.create_task(self._send_verification_pin(user.email, name, pin))

        access_token = create_access_token(
            user_id=str(user.id),
            scopes=["read", "write", "execute"],
            additional_claims={
                "tier": user.tier,
                "email": user.email,
            },
        )
        refresh_token = create_refresh_token(user_id=str(user.id))
        expires_in = get_settings().jwt_access_token_expire_minutes * 60

        return user, access_token, refresh_token, expires_in

    async def verify_email_pin(
        self,
        user_id: uuid.UUID,
        pin: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> User:
        """Verify a user's email with the 6-digit PIN.

        Raises:
            UserNotFoundError: If user not found.
            AlreadyVerifiedError: If already verified.
            VerificationPinExpiredError: If PIN has expired.
            VerificationAttemptsExceededError: If too many failed attempts.
            InvalidVerificationPinError: If PIN is wrong.
        """
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundError()

        if user.email_verified:
            raise AlreadyVerifiedError()

        if not user.verification_token or not user.verification_pin_expires_at:
            raise VerificationPinExpiredError()

        if user.verification_attempts >= 5:
            raise VerificationAttemptsExceededError()

        if datetime.now(UTC) >= user.verification_pin_expires_at:
            raise VerificationPinExpiredError()

        pin_hash = hashlib.sha256(pin.encode()).hexdigest()
        if pin_hash != user.verification_token:
            user.verification_attempts += 1
            audit_log = AuditLog(
                user_id=user.id,
                action=AuditAction.AUTH_FAILED.value,
                resource_type="user",
                resource_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                event_data={
                    "reason": "invalid_verification_pin",
                    "attempts": user.verification_attempts,
                },
            )
            self.db.add(audit_log)
            raise InvalidVerificationPinError()

        user.email_verified = True
        user.status = "active"
        user.verification_token = None
        user.verification_pin_expires_at = None
        user.verification_attempts = 0

        audit_log = AuditLog(
            user_id=user.id,
            action=AuditAction.USER_LOGIN.value,
            resource_type="user",
            resource_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            event_data={"method": "email_verification", "email": user.email},
        )
        self.db.add(audit_log)

        asyncio.create_task(self._send_welcome_after_verification(user.email, user.name))

        return user

    async def resend_verification_pin(
        self,
        user_id: uuid.UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> int:
        """Resend a new verification PIN.

        Returns:
            Number of resends remaining.

        Raises:
            UserNotFoundError: If user not found.
            AlreadyVerifiedError: If already verified.
            VerificationResendLimitError: If max resends reached.
        """
        max_resends = 5

        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundError()

        if user.email_verified:
            raise AlreadyVerifiedError()

        if user.verification_resend_count >= max_resends:
            raise VerificationResendLimitError()

        pin, pin_hash = self._generate_pin()

        user.verification_token = pin_hash
        user.verification_pin_expires_at = datetime.now(UTC) + timedelta(minutes=10)
        user.verification_attempts = 0
        user.verification_resend_count += 1

        audit_log = AuditLog(
            user_id=user.id,
            action=AuditAction.USER_LOGIN.value,
            resource_type="user",
            resource_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            event_data={
                "method": "resend_verification_pin",
                "resend_count": user.verification_resend_count,
            },
        )
        self.db.add(audit_log)

        asyncio.create_task(self._send_verification_pin(user.email, user.name, pin))

        return max_resends - user.verification_resend_count

    @staticmethod
    async def _send_verification_pin(email: str, name: str | None, pin: str) -> None:
        try:
            from mcpworks_api.services.email import send_verification_pin_email

            await send_verification_pin_email(email, name, pin)
        except Exception:
            logger.warning("verification_pin_email_failed", email=email)

    @staticmethod
    async def _send_welcome_after_verification(email: str, name: str | None) -> None:
        try:
            from mcpworks_api.services.email import send_welcome_email

            await send_welcome_email(email, name)
        except Exception:
            logger.warning("welcome_email_failed", email=email)

    async def login_user(
        self,
        email: str,
        password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[str, str, int]:
        """Authenticate a user with email and password.

        Args:
            email: User's email address.
            password: User's password.
            ip_address: Client IP address for audit logging.
            user_agent: Client user agent for audit logging.

        Returns:
            Tuple of (access_token, refresh_token, expires_in_seconds)

        Raises:
            InvalidCredentialsError: If email or password is invalid.
        """
        # Find user by email
        result = await self.db.execute(select(User).where(User.email == email.lower()))
        user = result.scalar_one_or_none()

        if not user:
            await self._log_auth_failure(None, ip_address, user_agent, "Email not found")
            raise InvalidCredentialsError()

        if not user.password_hash:
            await self._log_auth_failure(user.id, ip_address, user_agent, "OAuth-only account")
            raise InvalidCredentialsError(
                message="This account uses social login. Please sign in with your OAuth provider."
            )

        if not verify_password(password, user.password_hash):
            await self._log_auth_failure(user.id, ip_address, user_agent, "Invalid password")
            raise InvalidCredentialsError()

        if user.status == "rejected":
            await self._log_auth_failure(user.id, ip_address, user_agent, "Account rejected")
            raise InvalidCredentialsError(message="Account has not been approved")

        if user.status not in ("active", "pending_verification"):
            await self._log_auth_failure(user.id, ip_address, user_agent, "User inactive")
            raise InvalidCredentialsError(message="User account is not active")

        # Log successful login
        audit_log = AuditLog(
            user_id=user.id,
            action=AuditAction.USER_LOGIN.value,
            resource_type="user",
            resource_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            event_data={"method": "email_password"},
        )
        self.db.add(audit_log)

        # Create tokens
        access_token = create_access_token(
            user_id=str(user.id),
            scopes=["read", "write", "execute"],
            additional_claims={
                "tier": user.tier,
                "email": user.email,
            },
        )
        refresh_token = create_refresh_token(user_id=str(user.id))

        expires_in = get_settings().jwt_access_token_expire_minutes * 60

        return access_token, refresh_token, expires_in

    async def create_api_key(
        self,
        user_id: uuid.UUID,
        name: str | None = None,
        scopes: list[str] | None = None,
        namespace_id: uuid.UUID | None = None,
        expires_in_days: int | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[APIKey, str]:
        """Create a new API key for a user.

        Args:
            user_id: User's UUID.
            name: Optional human-readable label.
            scopes: Permissions granted to this key.
            namespace_id: Optional namespace to scope the key to.
            expires_in_days: Days until expiration (None = never).
            ip_address: Client IP address for audit logging.
            user_agent: Client user agent for audit logging.

        Returns:
            Tuple of (api_key_record, raw_api_key_string)

        Raises:
            UserNotFoundError: If user doesn't exist.
            NotFoundError: If namespace_id is given but doesn't exist.
            ForbiddenError: If namespace doesn't belong to user's account.
        """
        from sqlalchemy.orm import selectinload

        from mcpworks_api.models import Namespace

        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise UserNotFoundError()

        if namespace_id is not None:
            ns_result = await self.db.execute(select(Namespace).where(Namespace.id == namespace_id))
            namespace = ns_result.scalar_one_or_none()
            if not namespace:
                raise NotFoundError(message="Namespace not found")
            result = await self.db.execute(select(Account).where(Account.user_id == user_id))
            account = result.scalar_one_or_none()
            if not account or namespace.account_id != account.id:
                raise ForbiddenError(message="Namespace does not belong to this account")

        raw_key = generate_api_key(prefix="mcpw")
        key_prefix = raw_key[:12]
        key_hash = hash_api_key(raw_key)

        expires_at = None
        if expires_in_days:
            expires_at = datetime.now(UTC) + timedelta(days=expires_in_days)

        api_key = APIKey(
            user_id=user_id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            name=name,
            scopes=scopes or ["read", "write", "execute"],
            namespace_id=namespace_id,
            expires_at=expires_at,
        )
        self.db.add(api_key)
        await self.db.flush()

        if namespace_id:
            await self.db.execute(
                select(APIKey)
                .where(APIKey.id == api_key.id)
                .options(selectinload(APIKey.namespace))
            )

        audit_log = AuditLog(
            user_id=user_id,
            action=AuditAction.API_KEY_CREATED.value,
            resource_type="api_key",
            resource_id=api_key.id,
            ip_address=ip_address,
            user_agent=user_agent,
            event_data={
                "key_prefix": key_prefix,
                "scopes": api_key.scopes,
                "namespace_id": str(namespace_id) if namespace_id else None,
            },
        )
        self.db.add(audit_log)

        return api_key, raw_key

    async def list_api_keys(
        self,
        user_id: uuid.UUID,
        include_revoked: bool = False,
    ) -> list[APIKey]:
        """List API keys for a user.

        Args:
            user_id: User's UUID.
            include_revoked: Whether to include revoked keys.

        Returns:
            List of API key records (with namespace eager-loaded).
        """
        from sqlalchemy.orm import selectinload

        query = (
            select(APIKey).where(APIKey.user_id == user_id).options(selectinload(APIKey.namespace))
        )

        if not include_revoked:
            query = query.where(APIKey.revoked_at.is_(None))

        query = query.order_by(APIKey.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def revoke_api_key(
        self,
        user_id: uuid.UUID,
        key_id: uuid.UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> APIKey:
        """Revoke an API key.

        Args:
            user_id: User's UUID (must own the key).
            key_id: API key UUID to revoke.
            ip_address: Client IP address for audit logging.
            user_agent: Client user agent for audit logging.

        Returns:
            The revoked API key record.

        Raises:
            ApiKeyNotFoundError: If key doesn't exist or belongs to another user.
        """
        result = await self.db.execute(
            select(APIKey).where(APIKey.id == key_id).where(APIKey.user_id == user_id)
        )
        api_key = result.scalar_one_or_none()

        if not api_key:
            raise ApiKeyNotFoundError()

        if api_key.revoked_at is not None:
            raise ApiKeyNotFoundError(message="API key is already revoked")

        # Revoke the key
        api_key.revoked_at = datetime.now(UTC)

        # Log revocation
        audit_log = AuditLog(
            user_id=user_id,
            action=AuditAction.API_KEY_REVOKED.value,
            resource_type="api_key",
            resource_id=key_id,
            ip_address=ip_address,
            user_agent=user_agent,
            event_data={"key_prefix": api_key.key_prefix},
        )
        self.db.add(audit_log)

        return api_key
