"""
Checkout session request/response schemas.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from uuid import UUID


class CheckoutLineItem(BaseModel):
    """A single line item in the checkout."""
    name: str = Field(..., max_length=200, description="Product/item name shown on the checkout page")
    quantity: int = Field(default=1, ge=1, description="Number of units")
    price: int = Field(..., gt=0, description="Unit price in smallest currency unit (e.g., cents)")


class CheckoutSessionCreate(BaseModel):
    """Request body to create a hosted checkout session.

    The client only needs to send the payment details and redirect URLs.
    The response includes a checkout_url — redirect the end-user there.
    """
    line_items: List[CheckoutLineItem] = Field(
        ...,
        min_length=1,
        description="Items being purchased (displayed on the checkout page)",
    )
    currency: str = Field(default="usd", min_length=3, max_length=3, description="ISO 4217 currency code")
    success_url: str = Field(
        ...,
        description="URL to redirect the customer after successful payment.",
    )
    cancel_url: str = Field(
        ...,
        description="URL to redirect the customer if they cancel the checkout.",
    )
    customer_email: str = Field(..., description="Email of a pre-registered customer in the Payment Service")
    customer_name: Optional[str] = Field(default=None, description="Customer name shown on checkout UI")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Arbitrary key-value metadata passed to the payment")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "line_items": [
                        {"name": "VIP Concert Ticket", "quantity": 2, "price": 5000}
                    ],
                    "currency": "usd",
                    "success_url": "https://mytickets.com/order/123/success",
                    "cancel_url": "https://mytickets.com/order/123/cancel",
                    "customer_email": "alice@example.com",
                    "customer_name": "Alice Smith",
                    "metadata": {"order_id": "order_123", "event_id": "evt_456"},
                }
            ]
        }
    }


class CheckoutAuthorizeResponse(BaseModel):
    status: str = Field(..., description="Authorization status (e.g. 'succeeded')")
    payment_id: UUID = Field(..., description="ID of the completed internal payment")
    success_url: str = Field(..., description="URL to redirect the customer to upon success")


class CheckoutSessionResponse(BaseModel):
    """Response after creating a checkout session.

    Redirect the end-user's browser to `checkout_url` to complete payment.
    """
    session_id: str = Field(..., description="Checkout Session ID")
    line_items: Optional[List[CheckoutLineItem]] = Field(default=None, description="Items to display in the UI")
    checkout_url: str = Field(..., description="URL to redirect the customer to for payment")
    status: str = Field(..., description="Session status: open, complete, or expired")
    success_url: str = Field(..., description="URL to redirect on success")
    cancel_url: str = Field(..., description="URL to redirect on cancel")
    expires_at: datetime = Field(..., description="When this checkout session expires")
    payment_status: str = Field(..., description="Payment status: unpaid, paid, or no_payment_required")
    amount_total: int = Field(..., description="Total amount in smallest currency unit")
    currency: str = Field(..., description="ISO 4217 currency code")
    customer_name: str = Field(..., description="Customer name")
    customer_email: str = Field(..., description="Customer email")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Metadata")
