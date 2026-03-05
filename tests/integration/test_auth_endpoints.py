"""Integration tests for authentication endpoints - TDD tests written FIRST."""

from datetime import UTC, timedelta

import pytest
from httpx import AsyncClient

from mcpworks_api.core.security import (
    create_access_token,
    create_refresh_token,
    generate_api_key,
    hash_api_key,
)
from mcpworks_api.models import APIKey


@pytest.mark.asyncio
class TestTokenExchange:
    """Tests for POST /v1/auth/token endpoint."""

    async def test_token_exchange_valid_key(self, client: AsyncClient, db, make_user):
        """Valid API key should return 200 with access and refresh tokens."""
        # Create user and API key
        user = make_user(email="auth_test@example.com")
        db.add(user)
        await db.commit()

        # Generate real API key
        raw_key = generate_api_key()
        key_hash = hash_api_key(raw_key)
        api_key = APIKey(
            user_id=user.id,
            key_hash=key_hash,
            key_prefix=raw_key[:12],
            name="Test Key",
            scopes=["read", "write", "execute"],
        )
        db.add(api_key)
        await db.commit()

        # Exchange API key for tokens
        response = await client.post(
            "/v1/auth/token",
            json={"api_key": raw_key},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data

    async def test_token_exchange_invalid_key(self, client: AsyncClient):
        """Invalid API key should return 401 with INVALID_API_KEY error."""
        response = await client.post(
            "/v1/auth/token",
            json={"api_key": "mcp_invalid_key_that_does_not_exist"},
        )

        assert response.status_code == 401
        data = response.json()
        assert data["error"] == "INVALID_API_KEY"

    async def test_token_exchange_revoked_key(self, client: AsyncClient, db, make_user):
        """Revoked API key should return 401 with INVALID_API_KEY error."""
        from datetime import datetime

        # Create user and revoked API key
        user = make_user(email="revoked_test@example.com")
        db.add(user)
        await db.commit()

        raw_key = generate_api_key()
        key_hash = hash_api_key(raw_key)
        api_key = APIKey(
            user_id=user.id,
            key_hash=key_hash,
            key_prefix=raw_key[:12],
            name="Revoked Key",
            scopes=["read", "write"],
            revoked_at=datetime.now(UTC),  # Already revoked
        )
        db.add(api_key)
        await db.commit()

        response = await client.post(
            "/v1/auth/token",
            json={"api_key": raw_key},
        )

        assert response.status_code == 401
        data = response.json()
        assert data["error"] == "INVALID_API_KEY"

    async def test_token_exchange_expired_key(self, client: AsyncClient, db, make_user):
        """Expired API key should return 401 with INVALID_API_KEY error."""
        from datetime import datetime, timedelta

        # Create user and expired API key
        user = make_user(email="expired_test@example.com")
        db.add(user)
        await db.commit()

        raw_key = generate_api_key()
        key_hash = hash_api_key(raw_key)
        api_key = APIKey(
            user_id=user.id,
            key_hash=key_hash,
            key_prefix=raw_key[:12],
            name="Expired Key",
            scopes=["read", "write"],
            expires_at=datetime.now(UTC) - timedelta(hours=1),  # Already expired
        )
        db.add(api_key)
        await db.commit()

        response = await client.post(
            "/v1/auth/token",
            json={"api_key": raw_key},
        )

        assert response.status_code == 401
        data = response.json()
        assert data["error"] == "INVALID_API_KEY"


@pytest.mark.asyncio
class TestTokenRefresh:
    """Tests for POST /v1/auth/refresh endpoint."""

    async def test_refresh_token_valid(self, client: AsyncClient, db, make_user):
        """Valid refresh token should return 200 with new access token."""
        # Create user
        user = make_user(email="refresh_test@example.com")
        db.add(user)
        await db.commit()

        # Create refresh token
        refresh_token = create_refresh_token(str(user.id))

        response = await client.post(
            "/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_refresh_token_invalid(self, client: AsyncClient):
        """Invalid refresh token should return 401."""
        response = await client.post(
            "/v1/auth/refresh",
            json={"refresh_token": "invalid.token.here"},
        )

        assert response.status_code == 401

    async def test_refresh_token_expired(self, client: AsyncClient, db, make_user):
        """Expired refresh token should return 401 with TOKEN_EXPIRED."""
        user = make_user(email="expired_refresh@example.com")
        db.add(user)
        await db.commit()

        # Create expired refresh token
        refresh_token = create_refresh_token(
            str(user.id),
            expires_delta=timedelta(seconds=-1),
        )

        response = await client.post(
            "/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )

        assert response.status_code == 401
        data = response.json()
        # Could be TOKEN_EXPIRED or REFRESH_TOKEN_EXPIRED depending on impl
        assert "EXPIRED" in data["error"]


@pytest.mark.asyncio
class TestUsersMe:
    """Tests for GET /v1/users/me endpoint."""

    async def test_users_me_with_valid_jwt(self, client: AsyncClient, db, make_user):
        """Valid JWT should return 200 with user profile."""
        # Create user
        user = make_user(
            email="me_test@example.com",
            name="Test User",
            tier="pro",
        )
        db.add(user)
        await db.commit()

        # Create access token
        access_token = create_access_token(str(user.id))

        response = await client.get(
            "/v1/users/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "me_test@example.com"
        assert data["name"] == "Test User"
        assert data["tier"] == "pro"

    async def test_users_me_expired_jwt(self, client: AsyncClient, db, make_user):
        """Expired JWT should return 401 with TOKEN_EXPIRED."""
        user = make_user(email="expired_me@example.com")
        db.add(user)
        await db.commit()

        # Create expired access token
        access_token = create_access_token(
            str(user.id),
            expires_delta=timedelta(seconds=-1),
        )

        response = await client.get(
            "/v1/users/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 401
        data = response.json()
        assert data["error"] == "TOKEN_EXPIRED"

    async def test_users_me_no_token(self, client: AsyncClient):
        """Request without token should return 401."""
        response = await client.get("/v1/users/me")

        assert response.status_code == 401

    async def test_users_me_invalid_token(self, client: AsyncClient):
        """Invalid token should return 401 with INVALID_TOKEN."""
        response = await client.get(
            "/v1/users/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )

        assert response.status_code == 401
        data = response.json()
        assert data["error"] == "INVALID_TOKEN"


@pytest.mark.asyncio
class TestRateLimiting:
    """Tests for authentication rate limiting."""

    async def test_auth_rate_limit_exceeded(self, client: AsyncClient):
        """More than 5 auth failures in 1 minute should return 429.

        Note: The test client doesn't use RateLimitMiddleware (due to SQLAlchemy async
        session issues with BaseHTTPMiddleware), so we pre-seed Redis with the failure
        count to simulate previous failures.
        """
        from mcpworks_api.core.redis import get_redis_context

        # Pre-seed Redis with 5 auth failures (simulating previous failed attempts)
        # The test client uses 127.0.0.1 as the client IP
        async with get_redis_context() as redis:
            key = "ratelimit:auth_fail:127.0.0.1"
            await redis.set(key, "5")
            await redis.expire(key, 60)  # 1 minute window

        # Now the next request should be rate limited
        response = await client.post(
            "/v1/auth/token",
            json={"api_key": "mcp_invalid_key_test"},
        )

        assert response.status_code == 429
        data = response.json()
        assert data["error"] == "RATE_LIMIT_EXCEEDED"


@pytest.mark.asyncio
class TestUserRegistration:
    """Tests for POST /v1/auth/register endpoint."""

    async def test_register_success(self, client: AsyncClient, db):  # noqa: ARG002
        """Valid registration should return 201 with access token."""
        response = await client.post(
            "/v1/auth/register",
            json={
                "email": "newuser@example.com",
                "password": "SecurePass123",
                "name": "New User",
                "accept_tos": True,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert "user" in data
        assert data["user"]["email"] == "newuser@example.com"
        assert data["user"]["name"] == "New User"
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_register_duplicate_email(self, client: AsyncClient, db, make_user):
        """Duplicate email should return 409 with EMAIL_EXISTS error."""
        # Create existing user
        user = make_user(email="existing@example.com")
        db.add(user)
        await db.commit()

        response = await client.post(
            "/v1/auth/register",
            json={
                "email": "existing@example.com",
                "password": "SecurePass123",
                "accept_tos": True,
            },
        )

        assert response.status_code == 409
        data = response.json()
        assert data["error"] == "EMAIL_EXISTS"

    async def test_register_invalid_email(self, client: AsyncClient):
        """Invalid email format should return 422."""
        response = await client.post(
            "/v1/auth/register",
            json={
                "email": "not-a-valid-email",
                "password": "SecurePass123",
            },
        )

        assert response.status_code == 422

    async def test_register_password_too_short(self, client: AsyncClient):
        """Password shorter than 8 characters should return 422."""
        response = await client.post(
            "/v1/auth/register",
            json={
                "email": "test@example.com",
                "password": "short",
            },
        )

        assert response.status_code == 422

    async def test_register_without_name(self, client: AsyncClient, db):  # noqa: ARG002
        """Registration without name should succeed."""
        response = await client.post(
            "/v1/auth/register",
            json={
                "email": "noname@example.com",
                "password": "SecurePass123",
                "accept_tos": True,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["user"]["name"] is None


@pytest.mark.asyncio
class TestUserLogin:
    """Tests for POST /v1/auth/login endpoint."""

    async def test_login_success(self, client: AsyncClient, db, make_user):
        """Valid credentials should return 200 with tokens."""
        from mcpworks_api.core.security import hash_password

        # Create user with known password
        user = make_user(email="logintest@example.com")
        user.password_hash = hash_password("SecurePass123")
        db.add(user)
        await db.commit()

        response = await client.post(
            "/v1/auth/login",
            json={
                "email": "logintest@example.com",
                "password": "SecurePass123",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data

    async def test_login_invalid_email(self, client: AsyncClient):
        """Non-existent email should return 401."""
        response = await client.post(
            "/v1/auth/login",
            json={
                "email": "nonexistent@example.com",
                "password": "anypassword",
            },
        )

        assert response.status_code == 401
        data = response.json()
        assert data["error"] == "INVALID_CREDENTIALS"

    async def test_login_wrong_password(self, client: AsyncClient, db, make_user):
        """Wrong password should return 401."""
        from mcpworks_api.core.security import hash_password

        user = make_user(email="wrongpass@example.com")
        user.password_hash = hash_password("CorrectPass123")
        db.add(user)
        await db.commit()

        response = await client.post(
            "/v1/auth/login",
            json={
                "email": "wrongpass@example.com",
                "password": "WrongPass123",
            },
        )

        assert response.status_code == 401
        data = response.json()
        assert data["error"] == "INVALID_CREDENTIALS"

    async def test_login_inactive_user(self, client: AsyncClient, db, make_user):
        """Inactive user should return 401."""
        from mcpworks_api.core.security import hash_password

        user = make_user(email="inactive@example.com", status="suspended")
        user.password_hash = hash_password("SecurePass123")
        db.add(user)
        await db.commit()

        response = await client.post(
            "/v1/auth/login",
            json={
                "email": "inactive@example.com",
                "password": "SecurePass123",
            },
        )

        assert response.status_code == 401
        data = response.json()
        assert data["error"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
class TestApiKeyManagement:
    """Tests for API key management endpoints."""

    async def test_create_api_key(self, client: AsyncClient, db, make_user):
        """Authenticated user should be able to create API key."""
        user = make_user(email="apikey@example.com")
        db.add(user)
        await db.commit()

        access_token = create_access_token(str(user.id))

        response = await client.post(
            "/v1/users/me/api-keys",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "name": "My API Key",
                "scopes": ["read", "write"],
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert "key" in data
        assert data["key"].startswith("mcpw_")
        assert data["name"] == "My API Key"
        assert data["scopes"] == ["read", "write"]

    async def test_create_api_key_with_expiration(self, client: AsyncClient, db, make_user):
        """API key should support custom expiration."""
        user = make_user(email="expire@example.com")
        db.add(user)
        await db.commit()

        access_token = create_access_token(str(user.id))

        response = await client.post(
            "/v1/users/me/api-keys",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "name": "Expiring Key",
                "expires_in_days": 30,
            },
        )

        assert response.status_code == 201

    async def test_create_api_key_no_auth(self, client: AsyncClient):
        """Creating API key without auth should return 401."""
        response = await client.post(
            "/v1/users/me/api-keys",
            json={"name": "Unauthorized Key"},
        )

        assert response.status_code == 401

    async def test_list_api_keys(self, client: AsyncClient, db, make_user):
        """User should be able to list their API keys."""
        user = make_user(email="listkeys@example.com")
        db.add(user)
        await db.commit()

        # Create an API key
        raw_key = generate_api_key()
        key_hash = hash_api_key(raw_key)
        api_key = APIKey(
            user_id=user.id,
            key_hash=key_hash,
            key_prefix=raw_key[:12],
            name="Test Key",
            scopes=["read"],
        )
        db.add(api_key)
        await db.commit()

        access_token = create_access_token(str(user.id))

        response = await client.get(
            "/v1/users/me/api-keys",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1
        assert data["items"][0]["name"] == "Test Key"

    async def test_revoke_api_key(self, client: AsyncClient, db, make_user):
        """User should be able to revoke their API key."""
        user = make_user(email="revoke@example.com")
        db.add(user)
        await db.commit()

        # Create an API key
        raw_key = generate_api_key()
        key_hash = hash_api_key(raw_key)
        api_key = APIKey(
            user_id=user.id,
            key_hash=key_hash,
            key_prefix=raw_key[:12],
            name="To Be Revoked",
            scopes=["read"],
        )
        db.add(api_key)
        await db.commit()

        access_token = create_access_token(str(user.id))

        response = await client.delete(
            f"/v1/users/me/api-keys/{api_key.id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 204

        # Verify key can no longer be used
        response = await client.post(
            "/v1/auth/token",
            json={"api_key": raw_key},
        )
        assert response.status_code == 401

    async def test_revoke_nonexistent_key(self, client: AsyncClient, db, make_user):
        """Revoking non-existent key should return 404."""
        import uuid

        user = make_user(email="revokenotfound@example.com")
        db.add(user)
        await db.commit()

        access_token = create_access_token(str(user.id))

        response = await client.delete(
            f"/v1/users/me/api-keys/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 404

    async def test_revoke_other_users_key(self, client: AsyncClient, db, make_user):
        """User should not be able to revoke another user's key."""
        # Create two users
        user1 = make_user(email="user1@example.com")
        user2 = make_user(email="user2@example.com")
        db.add(user1)
        db.add(user2)
        await db.commit()

        # Create API key for user1
        raw_key = generate_api_key()
        key_hash = hash_api_key(raw_key)
        api_key = APIKey(
            user_id=user1.id,
            key_hash=key_hash,
            key_prefix=raw_key[:12],
            name="User1 Key",
            scopes=["read"],
        )
        db.add(api_key)
        await db.commit()

        # User2 tries to revoke user1's key
        access_token = create_access_token(str(user2.id))

        response = await client.delete(
            f"/v1/users/me/api-keys/{api_key.id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 404
