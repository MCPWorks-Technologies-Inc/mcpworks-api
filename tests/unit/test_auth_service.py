"""Unit tests for authentication service - TDD tests written FIRST."""

import re
from datetime import timedelta

import pytest

from mcpworks_api.core.exceptions import InvalidTokenError, TokenExpiredError
from mcpworks_api.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_access_token,
    verify_api_key,
    verify_password,
    verify_refresh_token,
)


class TestApiKeyGeneration:
    """Tests for API key generation and format validation."""

    def test_generate_api_key_format(self):
        """API key should match sk_{env}_{keyNum}_{random} format.

        Format: mcp_{64_hex_chars}
        Example: mcp_a1b2c3d4e5f6...
        """
        api_key = generate_api_key()

        # Should have correct prefix
        assert api_key.startswith("mcp_")

        # Should be correct total length (4 prefix + 64 hex = 68)
        assert len(api_key) == 68

        # Random part should be hex characters
        random_part = api_key[4:]
        assert re.match(r"^[a-f0-9]+$", random_part)

    def test_generate_api_key_unique(self):
        """Each generated API key should be unique."""
        keys = [generate_api_key() for _ in range(100)]
        assert len(set(keys)) == 100  # All unique

    def test_generate_api_key_custom_prefix(self):
        """API key should use custom prefix if provided."""
        api_key = generate_api_key(prefix="sk_test")
        assert api_key.startswith("sk_test_")


class TestApiKeyHashing:
    """Tests for API key hashing with Argon2id."""

    def test_hash_api_key_argon2id(self):
        """API key hash should use Argon2id algorithm."""
        api_key = "mcp_" + "a" * 64
        hashed = hash_api_key(api_key)

        # Argon2id hash starts with $argon2id$
        assert hashed.startswith("$argon2id$")

    def test_verify_api_key_success(self):
        """Valid API key should verify against its hash."""
        api_key = generate_api_key()
        hashed = hash_api_key(api_key)

        assert verify_api_key(api_key, hashed) is True

    def test_verify_api_key_wrong_key(self):
        """Wrong API key should fail verification."""
        api_key = generate_api_key()
        hashed = hash_api_key(api_key)
        wrong_key = generate_api_key()

        assert verify_api_key(wrong_key, hashed) is False

    def test_verify_api_key_invalid_hash(self):
        """Invalid hash should fail verification."""
        api_key = generate_api_key()
        invalid_hash = "not_a_valid_hash"

        assert verify_api_key(api_key, invalid_hash) is False


class TestJwtAccessToken:
    """Tests for ES256 JWT access token creation and validation."""

    def test_create_access_token_es256(self):
        """Access token should be created with ES256 algorithm."""
        user_id = "user_123"
        token = create_access_token(user_id)

        # Should be a valid JWT (3 parts separated by dots)
        parts = token.split(".")
        assert len(parts) == 3

    def test_create_access_token_contains_user_id(self):
        """Access token payload should contain user_id as subject."""
        user_id = "user_123"
        token = create_access_token(user_id)
        payload = decode_token(token)

        assert payload["sub"] == user_id

    def test_create_access_token_contains_type(self):
        """Access token payload should have type 'access'."""
        user_id = "user_123"
        token = create_access_token(user_id)
        payload = decode_token(token)

        assert payload["type"] == "access"

    def test_create_access_token_with_scopes(self):
        """Access token should include scopes if provided."""
        user_id = "user_123"
        scopes = ["read", "write"]
        token = create_access_token(user_id, scopes=scopes)
        payload = decode_token(token)

        assert payload["scopes"] == scopes

    def test_verify_access_token_success(self):
        """Valid access token should verify successfully."""
        user_id = "user_123"
        token = create_access_token(user_id)
        payload = verify_access_token(token)

        assert payload["sub"] == user_id

    def test_verify_access_token_wrong_type(self):
        """Refresh token should not verify as access token."""
        user_id = "user_123"
        refresh_token = create_refresh_token(user_id)

        with pytest.raises(InvalidTokenError) as exc_info:
            verify_access_token(refresh_token)

        assert "not an access token" in str(exc_info.value)


class TestJwtRefreshToken:
    """Tests for JWT refresh token creation and validation."""

    def test_create_refresh_token(self):
        """Refresh token should be created successfully."""
        user_id = "user_123"
        token = create_refresh_token(user_id)

        # Should be a valid JWT
        parts = token.split(".")
        assert len(parts) == 3

    def test_create_refresh_token_contains_type(self):
        """Refresh token payload should have type 'refresh'."""
        user_id = "user_123"
        token = create_refresh_token(user_id)
        payload = decode_token(token)

        assert payload["type"] == "refresh"

    def test_create_refresh_token_has_jti(self):
        """Refresh token should have unique JTI for revocation."""
        user_id = "user_123"
        token = create_refresh_token(user_id)
        payload = decode_token(token)

        assert "jti" in payload
        assert len(payload["jti"]) > 0

    def test_verify_refresh_token_success(self):
        """Valid refresh token should verify successfully."""
        user_id = "user_123"
        token = create_refresh_token(user_id)
        payload = verify_refresh_token(token)

        assert payload["sub"] == user_id

    def test_verify_refresh_token_wrong_type(self):
        """Access token should not verify as refresh token."""
        user_id = "user_123"
        access_token = create_access_token(user_id)

        with pytest.raises(InvalidTokenError) as exc_info:
            verify_refresh_token(access_token)

        assert "not a refresh token" in str(exc_info.value)


class TestTokenExpiration:
    """Tests for token expiration handling."""

    def test_validate_access_token_expired(self):
        """Expired access token should raise TokenExpiredError."""
        user_id = "user_123"
        # Create token that's already expired
        token = create_access_token(
            user_id,
            expires_delta=timedelta(seconds=-1),  # Already expired
        )

        with pytest.raises(TokenExpiredError):
            verify_access_token(token)

    def test_validate_refresh_token_expired(self):
        """Expired refresh token should raise TokenExpiredError."""
        user_id = "user_123"
        # Create token that's already expired
        token = create_refresh_token(
            user_id,
            expires_delta=timedelta(seconds=-1),  # Already expired
        )

        with pytest.raises(TokenExpiredError):
            verify_refresh_token(token)


class TestInvalidToken:
    """Tests for invalid token handling."""

    def test_decode_malformed_token(self):
        """Malformed token should raise InvalidTokenError."""
        with pytest.raises(InvalidTokenError):
            decode_token("not.a.valid.jwt")

    def test_decode_tampered_token(self):
        """Tampered token should raise InvalidTokenError."""
        user_id = "user_123"
        token = create_access_token(user_id)

        # Tamper with the payload
        parts = token.split(".")
        parts[1] = parts[1] + "tampered"
        tampered_token = ".".join(parts)

        with pytest.raises(InvalidTokenError):
            decode_token(tampered_token)


class TestPasswordHashing:
    """Tests for password hashing with Argon2id."""

    def test_hash_password_argon2id(self):
        """Password hash should use Argon2id algorithm."""
        password = "secure_password_123"
        hashed = hash_password(password)

        # Argon2id hash starts with $argon2id$
        assert hashed.startswith("$argon2id$")

    def test_verify_password_success(self):
        """Valid password should verify against its hash."""
        password = "secure_password_123"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_wrong_password(self):
        """Wrong password should fail verification."""
        password = "secure_password_123"
        hashed = hash_password(password)
        wrong_password = "wrong_password_456"

        assert verify_password(wrong_password, hashed) is False

    def test_verify_password_invalid_hash(self):
        """Invalid hash should fail verification."""
        password = "secure_password_123"
        invalid_hash = "not_a_valid_hash"

        assert verify_password(password, invalid_hash) is False

    def test_hash_password_unique_salts(self):
        """Same password should produce different hashes (different salts)."""
        password = "same_password"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        # Hashes should be different due to random salts
        assert hash1 != hash2

        # Both should verify correctly
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True
