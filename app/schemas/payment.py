"""
Payment request/response schemas.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PaymentCreate(BaseModel):
    """Request body to create a new payment."""
    amount: int = Field(..., gt=0, description="Amount in smallest currency unit (e.g., cents)")
    currency: str = Field(default="usd", min_length=3, max_length=3, description="ISO 4217 currency code")
    customer_id: Optional[UUID] = Field(default=None, description="ID of the customer in our system")
    payment_method_id: Optional[str] = Field(default=None, description="Stripe payment method ID (e.g., pm_card_visa)")
    description: Optional[str] = Field(default=None, max_length=500, description="Payment description")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Arbitrary key-value metadata")
    confirm: bool = Field(default=True, description="Whether to immediately confirm the payment")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "amount": 5000,
                    "currency": "usd",
                    "payment_method_id": "pm_card_visa",
                    "description": "Event ticket purchase",
                    "metadata": {"event_id": "evt_123", "ticket_type": "VIP"},
                    "confirm": True,
                }
            ]
        }
    }


class PaymentResponse(BaseModel):
    """Payment response body."""
    id: UUID
    stripe_payment_intent_id: Optional[str] = None
    customer_id: Optional[UUID] = None
    amount: int
    currency: str
    status: str
    description: Optional[str] = None
    payment_method_id: Optional[str] = None
    client_secret: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    amount_refunded: int = 0
    idempotency_key: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaymentListResponse(BaseModel):
    """Paginated list of payments."""
    items: List[PaymentResponse]
    total: int
    limit: int
    offset: int
    has_more: bool
