"""Unit tests for AuthService."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from mcpworks_api.core.exceptions import (
    ApiKeyNotFoundError,
    EmailExistsError,
    InvalidApiKeyError,
    InvalidCredentialsError,
    UserNotFoundError,
)
from mcpworks_api.core.security import hash_password
from mcpworks_api.models import APIKey, Credit, User
from mcpworks_api.services.auth import AuthService


@pytest.fixture
async def test_user(db):
    """Create a test user with hashed password."""
    user = User(
        email=f"test-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("testpassword123"),
        name="Test User",
        tier="free",
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


@pytest.fixture
async def test_user_with_credits(db, test_user):
    """Create a test user with credits."""
    credit = Credit(
        user_id=test_user.id,
        available_balance=Decimal("1000.00"),
        held_balance=Decimal("0.00"),
        lifetime_earned=Decimal("1000.00"),
        lifetime_spent=Decimal("0.00"),
    )
    db.add(credit)
    await db.flush()
    return test_user


@pytest.fixture
async def test_api_key(db, test_user):
    """Create a test API key and return both record and raw key."""
    auth_service = AuthService(db)
    api_key, raw_key = await auth_service.create_api_key(
        user_id=test_user.id,
        name="Test API Key",
        scopes=["read", "write", "execute"],
    )
    await db.commit()
    return api_key, raw_key


class TestAuthServiceRegister:
    """Tests for AuthService.register_user()."""

    @pytest.mark.asyncio
    async def test_register_user_basic(self, db):
        """Test registering a new user."""
        auth_service = AuthService(db)
        unique_email = f"newuser-{uuid.uuid4().hex[:8]}@example.com"

        user, access_token, refresh_token, expires_in = await auth_service.register_user(
            email=unique_email,
            password="securepassword123",
        )

        assert user.email == unique_email
        assert user.tier == "free"
        assert user.status == "active"
        assert access_token is not None
        assert refresh_token is not None
        assert expires_in > 0

    @pytest.mark.asyncio
    async def test_register_user_with_name(self, db):
        """Test registering user with name."""
        auth_service = AuthService(db)
        unique_email = f"named-{uuid.uuid4().hex[:8]}@example.com"

        user, _, _, _ = await auth_service.register_user(
            email=unique_email,
            password="securepassword123",
            name="John Doe",
        )

        assert user.name == "John Doe"

    @pytest.mark.asyncio
    async def test_register_user_email_normalized(self, db):
        """Test email is normalized to lowercase."""
        auth_service = AuthService(db)
        unique_suffix = uuid.uuid4().hex[:8]
        uppercase_email = f"UPPERCASE-{unique_suffix}@EXAMPLE.COM"

        user, _, _, _ = await auth_service.register_user(
            email=uppercase_email,
            password="securepassword123",
        )

        assert user.email == f"uppercase-{unique_suffix}@example.com"

    @pytest.mark.asyncio
    async def test_register_user_creates_credits(self, db):
        """Test registration creates credit record with free tier bonus."""
        auth_service = AuthService(db)
        unique_email = f"credituser-{uuid.uuid4().hex[:8]}@example.com"

        user, _, _, _ = await auth_service.register_user(
            email=unique_email,
            password="securepassword123",
        )
        await db.commit()
        await db.refresh(user, ["credit"])

        assert user.credit is not None
        assert user.credit.available_balance == Decimal("500.00")

    @pytest.mark.asyncio
    async def test_register_user_duplicate_email(self, db, test_user):
        """Test registering with existing email raises error."""
        auth_service = AuthService(db)

        with pytest.raises(EmailExistsError):
            await auth_service.register_user(
                email=test_user.email,
                password="differentpassword",
            )


class TestAuthServiceLogin:
    """Tests for AuthService.login_user()."""

    @pytest.mark.asyncio
    async def test_login_user_success(self, db, test_user):
        """Test successful login."""
        auth_service = AuthService(db)

        access_token, refresh_token, expires_in = await auth_service.login_user(
            email=test_user.email,
            password="testpassword123",
        )

        assert access_token is not None
        assert refresh_token is not None
        assert expires_in > 0

    @pytest.mark.asyncio
    async def test_login_user_wrong_password(self, db, test_user):
        """Test login with wrong password fails."""
        auth_service = AuthService(db)

        with pytest.raises(InvalidCredentialsError):
            await auth_service.login_user(
                email=test_user.email,
                password="wrongpassword",
            )

    @pytest.mark.asyncio
    async def test_login_user_nonexistent_email(self, db):
        """Test login with non-existent email fails."""
        auth_service = AuthService(db)

        with pytest.raises(InvalidCredentialsError):
            await auth_service.login_user(
                email="nonexistent@example.com",
                password="anypassword",
            )

    @pytest.mark.asyncio
    async def test_login_user_inactive(self, db):
        """Test login with inactive user fails."""
        # Create inactive user
        user = User(
            email=f"inactive-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("password123"),
            name="Inactive User",
            tier="free",
            status="suspended",
        )
        db.add(user)
        await db.flush()

        auth_service = AuthService(db)

        with pytest.raises(InvalidCredentialsError) as exc_info:
            await auth_service.login_user(
                email=user.email,
                password="password123",
            )

        assert "not active" in str(exc_info.value)


class TestAuthServiceApiKeyCreate:
    """Tests for AuthService.create_api_key()."""

    @pytest.mark.asyncio
    async def test_create_api_key_basic(self, db, test_user):
        """Test creating a basic API key."""
        auth_service = AuthService(db)

        api_key, raw_key = await auth_service.create_api_key(
            user_id=test_user.id,
        )

        assert api_key.user_id == test_user.id
        assert api_key.key_prefix == raw_key[:12]
        assert raw_key.startswith("mcpw_")
        assert api_key.scopes == ["read", "write", "execute"]

    @pytest.mark.asyncio
    async def test_create_api_key_with_name(self, db, test_user):
        """Test creating API key with name."""
        auth_service = AuthService(db)

        api_key, _ = await auth_service.create_api_key(
            user_id=test_user.id,
            name="Production Key",
        )

        assert api_key.name == "Production Key"

    @pytest.mark.asyncio
    async def test_create_api_key_with_scopes(self, db, test_user):
        """Test creating API key with custom scopes."""
        auth_service = AuthService(db)

        api_key, _ = await auth_service.create_api_key(
            user_id=test_user.id,
            scopes=["read"],
        )

        assert api_key.scopes == ["read"]

    @pytest.mark.asyncio
    async def test_create_api_key_with_expiration(self, db, test_user):
        """Test creating API key with expiration."""
        auth_service = AuthService(db)

        api_key, _ = await auth_service.create_api_key(
            user_id=test_user.id,
            expires_in_days=30,
        )

        assert api_key.expires_at is not None
        # Should expire in approximately 30 days
        expected = datetime.now(UTC) + timedelta(days=30)
        delta = abs((api_key.expires_at - expected).total_seconds())
        assert delta < 60  # Within 1 minute

    @pytest.mark.asyncio
    async def test_create_api_key_user_not_found(self, db):
        """Test creating API key for non-existent user fails."""
        auth_service = AuthService(db)

        with pytest.raises(UserNotFoundError):
            await auth_service.create_api_key(
                user_id=uuid.uuid4(),
            )


class TestAuthServiceApiKeyValidate:
    """Tests for AuthService.validate_api_key()."""

    @pytest.mark.asyncio
    async def test_validate_api_key_success(self, db, test_user, test_api_key):
        """Test validating a valid API key."""
        api_key, raw_key = test_api_key
        auth_service = AuthService(db)

        user = await auth_service.validate_api_key(raw_key)

        assert user.id == test_user.id

    @pytest.mark.asyncio
    async def test_validate_api_key_updates_last_used(self, db, test_user, test_api_key):
        """Test validation updates last_used_at timestamp."""
        api_key, raw_key = test_api_key
        api_key_id = api_key.id
        original_last_used = api_key.last_used_at

        auth_service = AuthService(db)
        await auth_service.validate_api_key(raw_key)
        await db.flush()
        db.expire_all()

        # Re-fetch the key to see the updated value
        from sqlalchemy import select

        result = await db.execute(select(APIKey).where(APIKey.id == api_key_id))
        updated_key = result.scalar_one()

        assert updated_key.last_used_at is not None
        if original_last_used:
            assert updated_key.last_used_at >= original_last_used

    @pytest.mark.asyncio
    async def test_validate_api_key_invalid_format(self, db):
        """Test validation fails for short key."""
        auth_service = AuthService(db)

        with pytest.raises(InvalidApiKeyError):
            await auth_service.validate_api_key("short")

    @pytest.mark.asyncio
    async def test_validate_api_key_wrong_key(self, db, test_api_key):
        """Test validation fails for wrong key."""
        auth_service = AuthService(db)

        with pytest.raises(InvalidApiKeyError):
            await auth_service.validate_api_key("mcp_wrongkeywrongkey")

    @pytest.mark.asyncio
    async def test_validate_api_key_expired(self, db, test_user):
        """Test validation fails for expired key."""
        auth_service = AuthService(db)

        # Create an already-expired key
        api_key, raw_key = await auth_service.create_api_key(
            user_id=test_user.id,
            expires_in_days=-1,  # Expired yesterday
        )
        await db.commit()

        with pytest.raises(InvalidApiKeyError) as exc_info:
            await auth_service.validate_api_key(raw_key)

        assert "expired" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validate_api_key_revoked(self, db, test_user, test_api_key):
        """Test validation fails for revoked key."""
        api_key, raw_key = test_api_key

        # Revoke the key
        api_key.revoked_at = datetime.now(UTC)
        await db.flush()

        auth_service = AuthService(db)

        with pytest.raises(InvalidApiKeyError):
            await auth_service.validate_api_key(raw_key)

    @pytest.mark.asyncio
    async def test_validate_api_key_inactive_user(self, db):
        """Test validation fails for inactive user's key."""
        # Create inactive user
        user = User(
            email=f"inactive-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("password123"),
            tier="free",
            status="suspended",
        )
        db.add(user)
        await db.flush()

        auth_service = AuthService(db)

        # Create API key for inactive user
        api_key, raw_key = await auth_service.create_api_key(user_id=user.id)
        await db.commit()

        with pytest.raises(InvalidApiKeyError) as exc_info:
            await auth_service.validate_api_key(raw_key)

        assert "not active" in str(exc_info.value)


class TestAuthServiceApiKeyList:
    """Tests for AuthService.list_api_keys()."""

    @pytest.mark.asyncio
    async def test_list_api_keys_empty(self, db, test_user):
        """Test listing API keys when none exist."""
        auth_service = AuthService(db)

        keys = await auth_service.list_api_keys(test_user.id)

        assert keys == []

    @pytest.mark.asyncio
    async def test_list_api_keys_multiple(self, db, test_user):
        """Test listing multiple API keys."""
        auth_service = AuthService(db)

        await auth_service.create_api_key(user_id=test_user.id, name="Key 1")
        await auth_service.create_api_key(user_id=test_user.id, name="Key 2")
        await auth_service.create_api_key(user_id=test_user.id, name="Key 3")

        keys = await auth_service.list_api_keys(test_user.id)

        assert len(keys) == 3

    @pytest.mark.asyncio
    async def test_list_api_keys_excludes_revoked(self, db, test_user):
        """Test listing excludes revoked keys by default."""
        auth_service = AuthService(db)

        api_key1, _ = await auth_service.create_api_key(user_id=test_user.id, name="Active Key")
        api_key2, _ = await auth_service.create_api_key(user_id=test_user.id, name="Revoked Key")
        await db.flush()

        # Revoke one key - the change is visible in the same session
        await auth_service.revoke_api_key(test_user.id, api_key2.id)
        await db.flush()

        keys = await auth_service.list_api_keys(test_user.id)

        assert len(keys) == 1
        assert keys[0].name == "Active Key"

    @pytest.mark.asyncio
    async def test_list_api_keys_include_revoked(self, db, test_user):
        """Test listing includes revoked keys when requested."""
        auth_service = AuthService(db)

        api_key1, _ = await auth_service.create_api_key(user_id=test_user.id, name="Active Key")
        api_key2, _ = await auth_service.create_api_key(user_id=test_user.id, name="Revoked Key")
        await db.flush()

        await auth_service.revoke_api_key(test_user.id, api_key2.id)

        keys = await auth_service.list_api_keys(test_user.id, include_revoked=True)

        assert len(keys) == 2


class TestAuthServiceApiKeyRevoke:
    """Tests for AuthService.revoke_api_key()."""

    @pytest.mark.asyncio
    async def test_revoke_api_key_success(self, db, test_user, test_api_key):
        """Test revoking an API key."""
        api_key, _ = test_api_key
        auth_service = AuthService(db)

        revoked = await auth_service.revoke_api_key(test_user.id, api_key.id)

        assert revoked.revoked_at is not None

    @pytest.mark.asyncio
    async def test_revoke_api_key_not_found(self, db, test_user):
        """Test revoking non-existent key fails."""
        auth_service = AuthService(db)

        with pytest.raises(ApiKeyNotFoundError):
            await auth_service.revoke_api_key(test_user.id, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_revoke_api_key_wrong_user(self, db, test_api_key):
        """Test revoking key belonging to different user fails."""
        api_key, _ = test_api_key
        auth_service = AuthService(db)

        with pytest.raises(ApiKeyNotFoundError):
            await auth_service.revoke_api_key(uuid.uuid4(), api_key.id)

    @pytest.mark.asyncio
    async def test_revoke_api_key_already_revoked(self, db, test_user, test_api_key):
        """Test revoking already-revoked key fails."""
        api_key, _ = test_api_key
        auth_service = AuthService(db)

        # Revoke once
        await auth_service.revoke_api_key(test_user.id, api_key.id)

        # Try to revoke again
        with pytest.raises(ApiKeyNotFoundError) as exc_info:
            await auth_service.revoke_api_key(test_user.id, api_key.id)

        assert "already revoked" in str(exc_info.value)


class TestAuthServiceTokenExchange:
    """Tests for token exchange methods."""

    @pytest.mark.asyncio
    async def test_exchange_api_key_for_tokens(self, db, test_user, test_api_key):
        """Test exchanging API key for JWT tokens."""
        _, raw_key = test_api_key
        auth_service = AuthService(db)

        access_token, refresh_token, expires_in = await auth_service.exchange_api_key_for_tokens(
            raw_key
        )

        assert access_token is not None
        assert refresh_token is not None
        assert expires_in > 0

    @pytest.mark.asyncio
    async def test_exchange_invalid_api_key(self, db):
        """Test exchanging invalid API key fails."""
        auth_service = AuthService(db)

        with pytest.raises(InvalidApiKeyError):
            await auth_service.exchange_api_key_for_tokens("mcp_invalidkeyhere")

    @pytest.mark.asyncio
    async def test_refresh_access_token(self, db, test_user, test_api_key):
        """Test refreshing access token."""
        _, raw_key = test_api_key
        auth_service = AuthService(db)

        # First, get tokens
        _, refresh_token, _ = await auth_service.exchange_api_key_for_tokens(raw_key)

        # Then refresh
        new_access_token, expires_in = await auth_service.refresh_access_token(refresh_token)

        assert new_access_token is not None
        assert expires_in > 0
