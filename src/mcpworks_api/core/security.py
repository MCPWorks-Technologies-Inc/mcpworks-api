"""Security utilities: password hashing and JWT token management."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from mcpworks_api.config import get_settings
from mcpworks_api.core.exceptions import InvalidTokenError, TokenExpiredError

# Argon2id configuration per spec (64MiB memory, 3 iterations, parallelism 4)
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MiB
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_api_key(api_key: str) -> str:
    """Hash an API key using Argon2id.

    Args:
        api_key: The plaintext API key to hash.

    Returns:
        The Argon2id hash string.
    """
    return _hasher.hash(api_key)


def verify_api_key(api_key: str, hashed: str) -> bool:
    """Verify an API key against its hash.

    Args:
        api_key: The plaintext API key to verify.
        hashed: The stored Argon2id hash.

    Returns:
        True if the API key matches, False otherwise.
    """
    try:
        _hasher.verify(hashed, api_key)
        return True
    except (InvalidHashError, VerificationError):
        return False


def check_needs_rehash(hashed: str) -> bool:
    """Check if a hash needs to be rehashed with updated parameters.

    Args:
        hashed: The stored hash to check.

    Returns:
        True if the hash should be updated.
    """
    return _hasher.check_needs_rehash(hashed)


def generate_api_key(prefix: str = "mcpw") -> str:
    """Generate a secure random API key.

    Format: {prefix}_{random_32_bytes_hex}
    Example: mcpw_a1b2c3d4e5f6...

    Args:
        prefix: The prefix for the API key.

    Returns:
        A new secure random API key.
    """
    random_part = secrets.token_hex(32)
    return f"{prefix}_{random_part}"


def hash_password(password: str) -> str:
    """Hash a password using Argon2id.

    Args:
        password: The plaintext password to hash.

    Returns:
        The Argon2id hash string.
    """
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash.

    Args:
        password: The plaintext password to verify.
        hashed: The stored Argon2id hash.

    Returns:
        True if the password matches, False otherwise.
    """
    try:
        _hasher.verify(hashed, password)
        return True
    except (InvalidHashError, VerificationError):
        return False


# ES256 JWT utilities
def _get_private_key() -> ec.EllipticCurvePrivateKey:
    """Load ES256 private key from env var or file."""
    key_pem = get_settings().jwt_private_key
    if not key_pem:
        # Try loading from file path
        key_path = get_settings().jwt_private_key_path
        if key_path.exists():
            key_pem = key_path.read_text()
        else:
            raise ValueError("JWT_PRIVATE_KEY not configured and key file not found")

    key = serialization.load_pem_private_key(
        key_pem.encode("utf-8"),
        password=None,
    )
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise ValueError("JWT private key must be an EC key for ES256")
    return key


def _get_public_key() -> ec.EllipticCurvePublicKey:
    """Load ES256 public key from env var or file."""
    key_pem = get_settings().jwt_public_key
    if not key_pem:
        # Try loading from file path
        key_path = get_settings().jwt_public_key_path
        if key_path.exists():
            key_pem = key_path.read_text()
        else:
            raise ValueError("JWT_PUBLIC_KEY not configured and key file not found")

    key = serialization.load_pem_public_key(key_pem.encode("utf-8"))
    if not isinstance(key, ec.EllipticCurvePublicKey):
        raise ValueError("JWT public key must be an EC key for ES256")
    return key


def create_access_token(
    user_id: str,
    scopes: list[str] | None = None,
    expires_delta: timedelta | None = None,
    additional_claims: dict[str, Any] | None = None,
) -> str:
    """Create a JWT access token with ES256 signing.

    Args:
        user_id: The user's unique identifier.
        scopes: Optional list of permission scopes.
        expires_delta: Optional custom expiration time.
        additional_claims: Optional additional JWT claims.

    Returns:
        The signed JWT token string.
    """
    now = datetime.now(UTC)

    if expires_delta is None:
        expires_delta = timedelta(minutes=get_settings().jwt_access_token_expire_minutes)

    expire = now + expires_delta

    payload = {
        "sub": user_id,
        "iat": now,
        "exp": expire,
        "iss": get_settings().jwt_issuer,
        "aud": get_settings().jwt_audience,
        "type": "access",
    }

    if scopes:
        payload["scopes"] = scopes

    if additional_claims:
        payload.update(additional_claims)

    private_key = _get_private_key()
    return jwt.encode(payload, private_key, algorithm="ES256")


def create_refresh_token(
    user_id: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT refresh token.

    Args:
        user_id: The user's unique identifier.
        expires_delta: Optional custom expiration time.

    Returns:
        The signed JWT refresh token string.
    """
    now = datetime.now(UTC)

    if expires_delta is None:
        expires_delta = timedelta(days=get_settings().jwt_refresh_token_expire_days)

    expire = now + expires_delta

    payload = {
        "sub": user_id,
        "iat": now,
        "exp": expire,
        "iss": get_settings().jwt_issuer,
        "aud": get_settings().jwt_audience,
        "type": "refresh",
        "jti": secrets.token_urlsafe(32),  # Unique token ID for revocation
    }

    private_key = _get_private_key()
    return jwt.encode(payload, private_key, algorithm="ES256")


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT token.

    Args:
        token: The JWT token string.

    Returns:
        The decoded token payload.

    Raises:
        TokenExpiredError: If the token has expired.
        InvalidTokenError: If the token is invalid.
    """
    try:
        public_key = _get_public_key()
        payload: dict[str, Any] = jwt.decode(
            token,
            public_key,
            algorithms=["ES256"],
            issuer=get_settings().jwt_issuer,
            audience=get_settings().jwt_audience,
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError()
    except jwt.InvalidTokenError as e:
        raise InvalidTokenError(message=str(e))


def verify_access_token(token: str) -> dict[str, Any]:
    """Verify an access token and return its payload.

    Args:
        token: The JWT access token string.

    Returns:
        The decoded token payload.

    Raises:
        TokenExpiredError: If the token has expired.
        InvalidTokenError: If the token is invalid or not an access token.
    """
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise InvalidTokenError(message="Token is not an access token")

    return payload


def verify_refresh_token(token: str) -> dict[str, Any]:
    """Verify a refresh token and return its payload.

    Args:
        token: The JWT refresh token string.

    Returns:
        The decoded token payload.

    Raises:
        TokenExpiredError: If the token has expired.
        InvalidTokenError: If the token is invalid or not a refresh token.
    """
    payload = decode_token(token)

    if payload.get("type") != "refresh":
        raise InvalidTokenError(message="Token is not a refresh token")

    return payload
