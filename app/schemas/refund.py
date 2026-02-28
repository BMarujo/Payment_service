"""
Refund request/response schemas.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class RefundCreate(BaseModel):
    """Request body to create a refund."""
    payment_id: UUID = Field(..., description="ID of the payment to refund")
    amount: Optional[int] = Field(default=None, gt=0, description="Refund amount in cents (default: full refund)")
    reason: str = Field(
        default="requested_by_customer",
        description="Refund reason: duplicate, fraudulent, requested_by_customer, other",
    )
    description: Optional[str] = Field(default=None, max_length=500, description="Additional details")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "payment_id": "550e8400-e29b-41d4-a716-446655440000",
                    "amount": 2500,
                    "reason": "requested_by_customer",
                    "description": "Customer changed mind about VIP upgrade",
                }
            ]
        }
    }


class RefundResponse(BaseModel):
    """Refund response body."""
    id: UUID
    stripe_refund_id: Optional[str] = None
    payment_id: UUID
    amount: int
    reason: str
    status: str
    description: Optional[str] = None
    idempotency_key: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RefundListResponse(BaseModel):
    """Paginated list of refunds."""
    items: List[RefundResponse]
    total: int
    limit: int
    offset: int
    has_more: bool
