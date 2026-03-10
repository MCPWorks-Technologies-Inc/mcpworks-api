"""Async SQLAlchemy database setup and session management."""

import ssl as _ssl
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from mcpworks_api.config import get_settings


def _normalize_database_url(url: str) -> tuple[str, dict[str, object]]:
    """Strip sslmode from URL and return (clean_url, connect_args).

    asyncpg doesn't accept ?sslmode=require — it uses its own ssl parameter.
    We strip sslmode/ssl from the query string and return connect_args with
    the appropriate ssl context.
    """
    connect_args: dict[str, object] = {
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
    }

    parts = urlsplit(url)
    ssl_needed = False

    if parts.query:
        params = parse_qs(parts.query)

        if "sslmode" in params:
            mode = params.pop("sslmode")[0]
            if mode in ("require", "verify-ca", "verify-full", "prefer"):
                ssl_needed = True

        if "ssl" in params:
            val = params.pop("ssl")[0]
            if val.lower() in ("true", "1", "yes"):
                ssl_needed = True

        new_query = urlencode(params, doseq=True)
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))

    hostname = (parts.hostname or "").lower()
    local_hosts = {"localhost", "127.0.0.1", "0.0.0.0", "postgres", "db"}
    if hostname and hostname not in local_hosts and not ssl_needed:
        ssl_needed = True

    if ssl_needed:
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
        connect_args["ssl"] = ctx

    return url, connect_args


# Lazily initialized engine and session factory
_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Get or create the async database engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        db_url, connect_args = _normalize_database_url(settings.database_url)
        _engine = create_async_engine(
            db_url,
            echo=settings.app_debug,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the async session factory."""
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _async_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides a database session.

    Usage:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    session = get_session_factory()()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for database sessions outside of request context.

    Usage:
        async with get_db_context() as db:
            ...
    """
    session = get_session_factory()()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def init_db() -> None:
    """Initialize database connection pool."""
    engine = get_engine()
    # Test connection
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))


async def close_db() -> None:
    """Close database connection pool."""
    global _engine, _async_session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
