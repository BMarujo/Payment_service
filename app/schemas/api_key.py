"""
API Key request/response schemas.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ApiKeyCreate(BaseModel):
    """Request body to create a new API key."""
    client_name: str = Field(..., min_length=1, max_length=255, description="Name of the client/tenant")
    description: Optional[str] = Field(default=None, max_length=500, description="Description of what this key is used for")
    scopes: Optional[List[str]] = Field(
        default=None,
        description=(
            "List of allowed scopes. If empty/null, all scopes are allowed. "
            "Available scopes: payments:read, payments:write, customers:read, customers:write"
        ),
    )
    rate_limit_requests: Optional[int] = Field(
        default=None, ge=1, le=10000,
        description="Custom rate limit (requests per window). Uses global default if not set.",
    )
    rate_limit_window_seconds: Optional[int] = Field(
        default=None, ge=1, le=3600,
        description="Custom rate limit window in seconds. Uses global default if not set.",
    )
    expires_at: Optional[datetime] = Field(
        default=None,
        description="Expiration timestamp (UTC). Null means the key never expires.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "client_name": "Ticket Service",
                    "description": "API key for the event ticketing microservice",
                    "scopes": ["payments:read", "payments:write", "customers:read"],
                    "rate_limit_requests": 200,
                    "rate_limit_window_seconds": 60,
                }
            ]
        }
    }


class ApiKeyUpdate(BaseModel):
    """Request body to update an API key."""
    description: Optional[str] = Field(default=None, max_length=500)
    scopes: Optional[List[str]] = Field(default=None)
    is_active: Optional[bool] = Field(default=None, description="Set to false to revoke the key")
    rate_limit_requests: Optional[int] = Field(default=None, ge=1, le=10000)
    rate_limit_window_seconds: Optional[int] = Field(default=None, ge=1, le=3600)
    expires_at: Optional[datetime] = Field(default=None)


class ApiKeyResponse(BaseModel):
    """API key details (without the raw key)."""
    id: UUID
    key_prefix: str = Field(description="First characters of the key for identification")
    client_name: str
    description: Optional[str] = None
    scopes: Optional[List[str]] = None
    is_active: bool
    rate_limit_requests: Optional[int] = None
    rate_limit_window_seconds: Optional[int] = None
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyCreatedResponse(ApiKeyResponse):
    """
    Response returned only at creation time.
    Contains the raw API key — this is the ONLY time the full key is shown.
    """
    raw_key: str = Field(description="The full API key. Store this securely — it cannot be retrieved again.")


class ApiKeyListResponse(BaseModel):
    """Paginated list of API keys."""
    items: List[ApiKeyResponse]
    total: int
    limit: int
    offset: int
    has_more: bool
