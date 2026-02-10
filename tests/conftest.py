"""Pytest configuration and shared fixtures."""

import contextlib
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from mcpworks_api.config import Settings, get_settings
from mcpworks_api.core import database as database_module
from mcpworks_api.core import redis as redis_module
from mcpworks_api.models.base import Base

# Generate test ES256 keys at module load
_test_private_key = ec.generate_private_key(ec.SECP256R1())
_test_private_key_pem = _test_private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode("utf-8")
_test_public_key_pem = (
    _test_private_key.public_key()
    .public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    .decode("utf-8")
)


# Test database URL (uses test database)
def get_test_settings() -> Settings:
    """Get settings configured for testing.

    Uses same database as dev (mcpworks) with tests running in transactions
    that get rolled back. Redis uses db 1 to avoid conflicts.

    Uses localhost when running locally, or Docker hostnames inside containers.
    """
    import os

    # Use localhost for local testing, Docker hostnames inside containers
    db_host = os.getenv("POSTGRES_HOST", "localhost")
    redis_host = os.getenv("REDIS_HOST", "localhost")

    return Settings(
        database_url=f"postgresql+asyncpg://mcpworks:mcpworks_dev@{db_host}:5432/mcpworks",
        redis_url=f"redis://{redis_host}:6379/1",
        app_debug=True,
        jwt_private_key=_test_private_key_pem,
        jwt_public_key=_test_public_key_pem,
    )


# Override settings for tests
@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Provide test settings."""
    return get_test_settings()


@pytest.fixture(autouse=True)
def setup_test_settings(monkeypatch):
    """Auto-apply test settings to all tests."""
    # Clear the lru_cache to ensure fresh settings
    get_settings.cache_clear()

    test_settings = get_test_settings()

    # Patch get_settings in all modules that import it
    monkeypatch.setattr("mcpworks_api.config.get_settings", lambda: test_settings)
    monkeypatch.setattr("mcpworks_api.core.security.get_settings", lambda: test_settings)
    monkeypatch.setattr("mcpworks_api.core.database.get_settings", lambda: test_settings)
    monkeypatch.setattr("mcpworks_api.services.stripe.get_settings", lambda: test_settings)

    # Reset Redis pool before each test to avoid stale connections
    redis_module._pool = None

    # Reset database module so API creates fresh connections with test settings
    database_module._engine = None
    database_module._async_session_factory = None


# Track if schema has been initialized
_schema_initialized = False


# Database engine for tests - function scoped to avoid cross-loop issues
@pytest_asyncio.fixture
async def test_engine(test_settings: Settings):
    """Create test database engine."""
    global _schema_initialized

    engine = create_async_engine(
        test_settings.database_url,
        poolclass=NullPool,
        echo=False,
    )

    # Only recreate schema once per test session
    if not _schema_initialized:
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
            await conn.run_sync(Base.metadata.create_all)
        _schema_initialized = True

    yield engine

    await engine.dispose()


# Session factory for tests
@pytest_asyncio.fixture
async def test_session_factory(test_engine):
    """Create test session factory."""
    return async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


# Database session fixture (per-test with data cleanup)
@pytest_asyncio.fixture
async def db(test_session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session for testing.

    Creates a fresh session for each test. Data is persisted during the test
    but gets cleaned up by table recreation between test runs.
    """
    session = test_session_factory()
    try:
        yield session
    finally:
        await session.close()


# FastAPI test client
@pytest_asyncio.fixture
async def client(test_settings: Settings, test_engine) -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client for testing endpoints.

    Creates a minimal app without BaseHTTPMiddleware which causes SQLAlchemy async session issues.
    See: https://github.com/tiangolo/fastapi/discussions/10379

    Depends on test_engine to ensure database schema is created first.
    """
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from mcpworks_api.api.v1 import router as v1_router
    from mcpworks_api.middleware import register_exception_handlers

    # Create minimal app without BaseHTTPMiddleware
    app = FastAPI(title="mcpworks API Test")

    # Only add CORS (which is NOT BaseHTTPMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register exception handlers
    register_exception_handlers(app)

    # Include routers
    app.include_router(v1_router)

    # Root endpoint (same as main.py)
    @app.get("/")
    async def root() -> dict[str, str]:
        return {
            "name": "mcpworks API",
            "version": "0.1.0",
            "docs": "/docs",
        }

    # Override settings for test configuration
    app.dependency_overrides[get_settings] = lambda: test_settings

    # Initialize Redis pool for this test (use test settings)
    # Clear Redis test database before each test to reset rate limits
    async with redis_module.get_redis_context() as redis_client:
        await redis_client.flushdb()

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client
    finally:
        # Clean up Redis pool after test completes
        if redis_module._pool is not None:
            with contextlib.suppress(Exception):
                await redis_module._pool.disconnect()
            redis_module._pool = None


# Fixture for creating test users
@pytest.fixture
def make_user():
    """Factory fixture for creating test users."""
    from mcpworks_api.models import User

    def _make_user(
        email: str = "test@example.com",
        name: str = "Test User",
        tier: str = "free",
        status: str = "active",
        **kwargs: Any,
    ) -> User:
        return User(
            email=email,
            password_hash="$argon2id$v=19$m=65536,t=3,p=4$test$testhash",
            name=name,
            tier=tier,
            status=status,
            **kwargs,
        )

    return _make_user


# Fixture for creating test API keys
@pytest.fixture
def make_api_key():
    """Factory fixture for creating test API keys."""
    from mcpworks_api.models import APIKey

    def _make_api_key(
        user_id,
        key_hash: str = "test_hash",
        key_prefix: str = "sk_test_k1_",
        name: str = "Test Key",
        scopes: list[str] = None,
        **kwargs: Any,
    ) -> APIKey:
        return APIKey(
            user_id=user_id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            name=name,
            scopes=scopes or ["read", "write", "execute"],
            **kwargs,
        )

    return _make_api_key
