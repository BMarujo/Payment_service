"""
Customer request/response schemas.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class CustomerCreate(BaseModel):
    """Request body to create a customer."""
    email: EmailStr = Field(..., description="Customer email address")
    name: Optional[str] = Field(default=None, max_length=255, description="Customer full name")
    phone: Optional[str] = Field(default=None, max_length=50, description="Customer phone number")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Arbitrary key-value metadata")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "email": "john.doe@example.com",
                    "name": "John Doe",
                    "phone": "+1234567890",
                    "metadata": {"external_id": "user_123"},
                }
            ]
        }
    }


class CustomerUpdate(BaseModel):
    """Request body to update a customer."""
    email: Optional[EmailStr] = Field(default=None, description="Customer email address")
    name: Optional[str] = Field(default=None, max_length=255, description="Customer full name")
    phone: Optional[str] = Field(default=None, max_length=50, description="Customer phone number")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Arbitrary key-value metadata")


class CustomerResponse(BaseModel):
    """Customer response body."""
    id: UUID
    stripe_customer_id: Optional[str] = None
    email: str
    name: Optional[str] = None
    phone: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CustomerListResponse(BaseModel):
    """Paginated list of customers."""
    items: List[CustomerResponse]
    total: int
    limit: int
    offset: int
    has_more: bool
