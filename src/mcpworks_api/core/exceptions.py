"""Custom exception classes for mcpworks API."""

from typing import Any


class MCPWorksException(Exception):
    """Base exception for mcpworks API errors."""

    error_code: str = "INTERNAL_ERROR"
    status_code: int = 500
    message: str = "An unexpected error occurred"

    def __init__(
        self,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to API error response format."""
        return {
            "error": self.error_code,
            "message": self.message,
            "details": self.details,
        }


# Authentication Errors (401)
class InvalidApiKeyError(MCPWorksException):
    """Raised when API key is invalid, revoked, or expired."""

    error_code = "INVALID_API_KEY"
    status_code = 401
    message = "Invalid or revoked API key"


class TokenExpiredError(MCPWorksException):
    """Raised when JWT token has expired."""

    error_code = "TOKEN_EXPIRED"
    status_code = 401
    message = "Access token has expired"


class InvalidTokenError(MCPWorksException):
    """Raised when JWT token is malformed or invalid."""

    error_code = "INVALID_TOKEN"
    status_code = 401
    message = "Invalid access token"


class InvalidCredentialsError(MCPWorksException):
    """Raised when email/password combination is invalid."""

    error_code = "INVALID_CREDENTIALS"
    status_code = 401
    message = "Invalid email or password"


class RefreshTokenExpiredError(MCPWorksException):
    """Raised when refresh token has expired."""

    error_code = "REFRESH_TOKEN_EXPIRED"
    status_code = 401
    message = "Refresh token has expired"


# Authorization Errors (403)
class InsufficientTierError(MCPWorksException):
    """Raised when user's tier doesn't permit the requested action."""

    error_code = "INSUFFICIENT_TIER"
    status_code = 403
    message = "Your subscription tier does not permit this action"


class InsufficientScopeError(MCPWorksException):
    """Raised when API key doesn't have required scope."""

    error_code = "INSUFFICIENT_SCOPE"
    status_code = 403
    message = "API key does not have required scope"


# Credit Errors (400)
class InsufficientCreditsError(MCPWorksException):
    """Raised when user doesn't have enough credits."""

    error_code = "INSUFFICIENT_CREDITS"
    status_code = 400
    message = "Insufficient credits for this operation"

    def __init__(
        self,
        required: float,
        available: float,
        message: str | None = None,
    ) -> None:
        details = {"required": required, "available": available}
        super().__init__(
            message=message or f"Insufficient credits: {available} available, {required} required",
            details=details,
        )


class InvalidHoldError(MCPWorksException):
    """Raised when credit hold is invalid or already processed."""

    error_code = "INVALID_HOLD"
    status_code = 400
    message = "Invalid or already processed credit hold"

    def __init__(
        self,
        hold_id: str,
        reason: str,
        message: str | None = None,
    ) -> None:
        details = {"hold_id": hold_id, "reason": reason}
        super().__init__(
            message=message or f"Invalid hold {hold_id}: {reason}",
            details=details,
        )


class CreditLockError(MCPWorksException):
    """Raised when credit row lock cannot be acquired."""

    error_code = "CREDIT_LOCK_ERROR"
    status_code = 409
    message = "Unable to acquire credit lock, please retry"


# Resource Errors (404, 409)
class UserNotFoundError(MCPWorksException):
    """Raised when user doesn't exist."""

    error_code = "USER_NOT_FOUND"
    status_code = 404
    message = "User not found"


class ApiKeyNotFoundError(MCPWorksException):
    """Raised when API key doesn't exist."""

    error_code = "API_KEY_NOT_FOUND"
    status_code = 404
    message = "API key not found"


class EmailExistsError(MCPWorksException):
    """Raised when email is already registered."""

    error_code = "EMAIL_EXISTS"
    status_code = 409
    message = "Email address is already registered"


# Service Errors (503)
class ServiceUnavailableError(MCPWorksException):
    """Raised when backend service is unavailable."""

    error_code = "SERVICE_UNAVAILABLE"
    status_code = 503
    message = "Service temporarily unavailable"

    def __init__(
        self,
        service_name: str,
        retry_after: int = 30,
        message: str | None = None,
    ) -> None:
        details = {"service": service_name, "retry_after": retry_after}
        super().__init__(
            message=message or f"Service '{service_name}' is temporarily unavailable",
            details=details,
        )
        self.retry_after = retry_after


class ServiceTimeoutError(MCPWorksException):
    """Raised when backend service times out."""

    error_code = "SERVICE_TIMEOUT"
    status_code = 504
    message = "Service request timed out"


# Rate Limiting (429)
class RateLimitExceededError(MCPWorksException):
    """Raised when rate limit is exceeded."""

    error_code = "RATE_LIMIT_EXCEEDED"
    status_code = 429
    message = "Rate limit exceeded"

    def __init__(
        self,
        limit: int,
        window: str,
        retry_after: int,
        message: str | None = None,
    ) -> None:
        details = {"limit": limit, "window": window, "retry_after": retry_after}
        super().__init__(
            message=message or f"Rate limit exceeded: {limit} requests per {window}",
            details=details,
        )
        self.retry_after = retry_after


# Validation Errors (422)
class ValidationError(MCPWorksException):
    """Raised for input validation errors."""

    error_code = "VALIDATION_ERROR"
    status_code = 422
    message = "Validation error"
