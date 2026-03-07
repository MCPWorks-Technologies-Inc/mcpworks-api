"""FastAPI application entry point."""

import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import structlog
from authlib.integrations.starlette_client import OAuth
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from mcpworks_api.api.v1 import router as v1_router
from mcpworks_api.config import get_settings
from mcpworks_api.core.database import close_db, get_db, init_db
from mcpworks_api.core.redis import close_redis, init_redis
from mcpworks_api.mcp.transport import MCPTransportMiddleware, session_manager
from mcpworks_api.middleware import (
    BillingMiddleware,
    CorrelationIdMiddleware,
    RequestLoggingMiddleware,
    SubdomainMiddleware,
    register_exception_handlers,
)
from mcpworks_api.middleware.metrics import setup_metrics
from mcpworks_api.middleware.rate_limit import RateLimitMiddleware


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager.

    Handles startup and shutdown events:
    - Startup: Initialize database, Redis, and MCP session manager
    - Shutdown: Close all connections gracefully
    """
    # Startup
    await init_db()
    await init_redis()

    async with session_manager.run():
        yield

    # Shutdown
    await close_db()
    await close_redis()


def _configure_logging(log_level: str) -> None:
    """ORDER-021: Configure structlog for JSON output with stdlib integration."""

    def _strip_env_vars(
        _logger: Any, _method_name: str, event_dict: dict[str, Any]
    ) -> dict[str, Any]:
        for key in ("sandbox_env", "env_vars", "env_dict"):
            event_dict.pop(key, None)
        return event_dict

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        _strip_env_vars,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, log_level, logging.INFO))

    for noisy in ("uvicorn.access", "uvicorn.error", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    settings = get_settings()

    # ORDER-021: Configure structured JSON logging via structlog
    _configure_logging(settings.log_level)

    # Initialize OAuth registry for social login providers
    from mcpworks_api.core.oauth_cache import RedisOAuthCache

    oauth_cache = RedisOAuthCache()
    oauth = OAuth(cache=oauth_cache)

    if settings.oauth_google_client_id:
        oauth.register(
            name="google",
            client_id=settings.oauth_google_client_id,
            client_secret=settings.oauth_google_client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"},
        )

    if settings.oauth_github_client_id:
        oauth.register(
            name="github",
            client_id=settings.oauth_github_client_id,
            client_secret=settings.oauth_github_client_secret,
            authorize_url="https://github.com/login/oauth/authorize",
            access_token_url="https://github.com/login/oauth/access_token",
            api_base_url="https://api.github.com/",
            client_kwargs={"scope": "user:email"},
        )

    # ORDER-013: Initialize Sentry error tracking
    if settings.sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.app_env,
            traces_sample_rate=0.1,
            profiles_sample_rate=0.1,
            send_default_pii=False,
        )
    app = FastAPI(
        title="mcpworks API",
        description="API Gateway for mcpworks platform - authentication, credit accounting, and service routing",
        version="0.1.0",
        docs_url="/docs" if settings.app_debug else None,
        redoc_url="/redoc" if settings.app_debug else None,
        openapi_url="/openapi.json" if settings.app_debug else None,
        lifespan=lifespan,
    )

    # Store OAuth registry on app state for route access
    app.state.oauth = oauth

    # Add middleware (order matters - first added = last executed on request)
    # So add in reverse order of desired execution:
    # 1. Subdomain Parsing → 2. Rate Limiting → 3. Billing (innermost)

    # MCP transport middleware (innermost - intercepts /mcp before routing)
    app.add_middleware(MCPTransportMiddleware)

    # Billing middleware
    # Tracks usage and enforces quotas for run endpoints
    app.add_middleware(BillingMiddleware)

    # Rate limiting middleware
    app.add_middleware(RateLimitMiddleware)

    # Subdomain parsing (A0: namespace + endpoint type extraction)
    app.add_middleware(SubdomainMiddleware)

    # ORDER-021: Structured per-request logging (runs after correlation ID is set)
    app.add_middleware(RequestLoggingMiddleware)

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

    # OAuth Protected Resource metadata (RFC 9728)
    # Claude Code probes this before connecting via MCP HTTP transport.
    # Minimal response: no authorization_servers = use Bearer token directly.
    @app.get("/.well-known/oauth-protected-resource")
    async def oauth_protected_resource() -> dict[str, str]:
        """Return minimal OAuth protected resource metadata."""
        return {"resource": "https://mcpworks.io"}

    # Admin HTML page — restricted to api.mcpworks.io + requires admin auth
    _admin_html_path = Path(__file__).parent / "static" / "admin.html"
    _admin_domains = {"api.mcpworks.io"}

    @app.get("/admin", include_in_schema=False)
    async def admin_page(request: Request):
        """Serve the admin dashboard — domain-restricted and auth-gated."""
        host = request.headers.get("host", "").lower().split(":")[0]
        is_local = host in ("localhost", "127.0.0.1", "0.0.0.0")
        if not is_local and host not in _admin_domains:
            return JSONResponse(status_code=404, content={"detail": "Not found"})

        from mcpworks_api.dependencies import get_current_user_id, require_admin

        try:
            authorization = request.headers.get("authorization")
            user_id = await get_current_user_id(authorization)
            db_gen = get_db()
            db = await db_gen.__anext__()
            try:
                await require_admin(user_id, db)
            finally:
                await db_gen.aclose()
        except Exception:
            return HTMLResponse(
                content='<!DOCTYPE html><html><head><meta charset="utf-8"><title>Admin</title></head>'
                "<body><h3>Admin Login Required</h3>"
                "<p>Authenticate with a valid admin token to access this page.</p>"
                "</body></html>",
                status_code=401,
            )

        return HTMLResponse(content=_admin_html_path.read_text())

    @app.get("/register", include_in_schema=False)
    async def register_page() -> RedirectResponse:
        """Redirect to console (registration is now inline)."""
        return RedirectResponse(url="/console#register", status_code=302)

    @app.get("/onboarding", include_in_schema=False)
    async def onboarding_page() -> RedirectResponse:
        """Redirect to console."""
        return RedirectResponse(url="/console", status_code=302)

    @app.get("/login", include_in_schema=False)
    async def login_page() -> RedirectResponse:
        """Redirect to console (login is now inline)."""
        return RedirectResponse(url="/console", status_code=302)

    # Client console (account dashboard)
    _console_html_path = Path(__file__).parent / "static" / "console.html"

    @app.get("/console", response_class=HTMLResponse, include_in_schema=False)
    async def console_page() -> HTMLResponse:
        """Serve the client console page."""
        return HTMLResponse(content=_console_html_path.read_text())

    # ORDER-016: Usage dashboard
    _dashboard_html_path = Path(__file__).parent / "static" / "dashboard.html"

    @app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard_page() -> HTMLResponse:
        """Serve the usage dashboard page."""
        return HTMLResponse(content=_dashboard_html_path.read_text())

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
