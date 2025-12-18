"""Test factories for User and APIKey models."""

import uuid
from datetime import datetime, timezone

import factory

from mcpworks_api.models import APIKey, User, UserStatus, UserTier


class UserFactory(factory.Factory):
    """Factory for creating test User instances."""

    class Meta:
        model = User

    id = factory.LazyFunction(uuid.uuid4)
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    password_hash = "$argon2id$v=19$m=65536,t=3,p=4$salt$hash"  # Dummy hash
    name = factory.Sequence(lambda n: f"Test User {n}")
    tier = UserTier.FREE.value
    status = UserStatus.ACTIVE.value
    email_verified = False
    verification_token = None
    created_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    updated_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))


class ActiveUserFactory(UserFactory):
    """Factory for creating active verified users."""

    status = UserStatus.ACTIVE.value
    email_verified = True


class ProUserFactory(UserFactory):
    """Factory for creating pro tier users."""

    tier = UserTier.PRO.value
    status = UserStatus.ACTIVE.value
    email_verified = True


class APIKeyFactory(factory.Factory):
    """Factory for creating test APIKey instances."""

    class Meta:
        model = APIKey

    id = factory.LazyFunction(uuid.uuid4)
    user_id = factory.LazyFunction(uuid.uuid4)
    key_hash = factory.Sequence(lambda n: f"hash_{n}")
    key_prefix = factory.Sequence(lambda n: f"sk_test_k{n}_")
    name = factory.Sequence(lambda n: f"Test Key {n}")
    scopes = ["read", "write", "execute"]
    created_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))
    last_used_at = None
    expires_at = None
    revoked_at = None


class RevokedAPIKeyFactory(APIKeyFactory):
    """Factory for creating revoked API keys."""

    revoked_at = factory.LazyFunction(lambda: datetime.now(timezone.utc))
