"""FastAPI application entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mcpworks_api.api.v1 import router as v1_router
from mcpworks_api.config import get_settings
from mcpworks_api.core.database import close_db, init_db
from mcpworks_api.core.redis import close_redis, init_redis
from mcpworks_api.middleware import CorrelationIdMiddleware, register_exception_handlers
from mcpworks_api.middleware.metrics import setup_metrics
from mcpworks_api.middleware.rate_limit import RateLimitMiddleware


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager.

    Handles startup and shutdown events:
    - Startup: Initialize database and Redis connections
    - Shutdown: Close all connections gracefully
    """
    # Startup
    await init_db()
    await init_redis()

    yield

    # Shutdown
    await close_db()
    await close_redis()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    settings = get_settings()
    app = FastAPI(
        title="mcpworks API",
        description="API Gateway for mcpworks platform - authentication, credit accounting, and service routing",
        version="0.1.0",
        docs_url="/docs" if settings.app_debug else None,
        redoc_url="/redoc" if settings.app_debug else None,
        openapi_url="/openapi.json" if settings.app_debug else None,
        lifespan=lifespan,
    )

    # Add middleware (order matters - first added = last executed)
    # Rate limiting middleware (outermost)
    app.add_middleware(RateLimitMiddleware)

    # Correlation ID middleware
    app.add_middleware(CorrelationIdMiddleware)

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register exception handlers
    register_exception_handlers(app)

    # Include routers
    app.include_router(v1_router)

    # Setup Prometheus metrics (after routers so routes are available)
    if settings.prometheus_enabled:
        setup_metrics(app)

    # Root endpoint
    @app.get("/")
    async def root() -> dict[str, str]:
        """Root endpoint with API information."""
        return {
            "name": "mcpworks API",
            "version": "0.1.0",
            "docs": "/docs" if settings.app_debug else "disabled",
        }

    return app


# Create the application instance
app = create_app()


def run() -> None:
    """Run the application with uvicorn.

    Used by the CLI entry point defined in pyproject.toml.
    """
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "mcpworks_api.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
        log_level="debug" if settings.app_debug else "info",
    )


if __name__ == "__main__":
    run()
