"""Global exception handlers for FastAPI application."""

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from mcpworks_api.core.exceptions import MCPWorksException

logger = structlog.get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers with the FastAPI app.

    Args:
        app: FastAPI application instance.
    """

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        _request: Request,
        exc: HTTPException,
    ) -> JSONResponse:
        """Handle HTTPException with flat response format.

        If detail is a dict (from our exceptions), return it directly.
        Otherwise wrap in standard format.
        """
        if exc.status_code >= 500:
            logger.error(
                "http_exception",
                status=exc.status_code,
                path=_request.url.path,
                method=_request.method,
            )
        elif exc.status_code >= 400:
            logger.warning(
                "http_exception",
                status=exc.status_code,
                path=_request.url.path,
                method=_request.method,
            )

        if isinstance(exc.detail, dict):
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.detail,
                headers=getattr(exc, "headers", None),
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "HTTP_ERROR",
                "message": str(exc.detail),
                "details": {},
            },
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(MCPWorksException)
    async def mcpworks_exception_handler(
        _request: Request,
        exc: MCPWorksException,
    ) -> JSONResponse:
        """Handle custom MCPWorks exceptions.

        Returns standardized error response format.
        """
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
        )

    @app.exception_handler(ValidationError)
    async def validation_exception_handler(
        _request: Request,
        exc: ValidationError,
    ) -> JSONResponse:
        """Handle Pydantic validation errors.

        Converts to standardized error format.
        """
        field_names = [".".join(str(p) for p in e["loc"]) for e in exc.errors()]
        logger.warning(
            "validation_error",
            path=_request.url.path,
            method=_request.method,
            error_count=len(exc.errors()),
            fields=field_names,
        )
        return JSONResponse(
            status_code=422,
            content={
                "error": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": {"errors": exc.errors()},
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """Handle unexpected exceptions.

        Logs the error and returns a generic 500 response.
        Does not expose internal details for security.
        """
        logger.exception(
            "unhandled_exception",
            exc_type=type(exc).__name__,
            exc_message=str(exc)[:500],
            path=request.url.path,
            method=request.method,
        )

        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "details": {},
            },
        )
