"""
Receipt response schema.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ReceiptResponse(BaseModel):
    """Receipt metadata response (PDF is returned separately)."""
    id: UUID
    payment_id: UUID
    receipt_number: str
    created_at: datetime

    model_config = {"from_attributes": True}
