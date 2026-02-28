"""
Common schemas: pagination, errors, success responses.
"""

from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationParams(BaseModel):
    """Query parameters for paginated listings."""
    limit: int = Field(default=20, ge=1, le=100, description="Items per page")
    offset: int = Field(default=0, ge=0, description="Number of items to skip")


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard paginated response wrapper."""
    items: List[Any] = Field(description="List of items")
    total: int = Field(description="Total number of items")
    limit: int = Field(description="Items per page")
    offset: int = Field(description="Current offset")
    has_more: bool = Field(description="Whether more items exist")


class ErrorDetail(BaseModel):
    """RFC 7807 Problem Details for HTTP APIs."""
    type: str = Field(default="about:blank", description="Error type URI")
    title: str = Field(description="Short human-readable summary")
    status: int = Field(description="HTTP status code")
    detail: Optional[str] = Field(default=None, description="Detailed explanation")
    instance: Optional[str] = Field(default=None, description="URI of the failing request")


class ErrorResponse(BaseModel):
    """Wrapper for error responses."""
    error: ErrorDetail


class SuccessResponse(BaseModel):
    """Generic success response."""
    status: str = Field(default="success")
    message: str = Field(description="Success message")
