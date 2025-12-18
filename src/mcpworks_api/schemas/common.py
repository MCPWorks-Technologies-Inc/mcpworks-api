"""Common Pydantic schemas used across the API."""

from typing import Any

from pydantic import BaseModel, ConfigDict


class SuccessResponse(BaseModel):
    """Standard success response wrapper."""

    model_config = ConfigDict(from_attributes=True)

    success: bool = True
    data: Any = None
    message: str | None = None


class ErrorResponse(BaseModel):
    """Standard error response format.

    Matches the MCPWorksException.to_dict() format.
    """

    error: str
    message: str
    details: dict[str, Any] = {}


class PaginatedResponse(BaseModel):
    """Paginated list response wrapper."""

    model_config = ConfigDict(from_attributes=True)

    items: list[Any]
    total: int
    page: int
    page_size: int
    total_pages: int

    @property
    def has_next(self) -> bool:
        """Check if there's a next page."""
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        """Check if there's a previous page."""
        return self.page > 1
