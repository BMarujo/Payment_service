"""
CheckoutSession model — stores data for our custom hosted checkout page.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Text,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class CheckoutSession(Base):
    __tablename__ = "checkout_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status = Column(String(50), nullable=False, default="open", index=True)

    # Line items (stored as JSON)
    line_items = Column(JSONB, nullable=False)
    
    # Total calculation
    amount_total = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False, default="usd")

    # Redirect URLs
    success_url = Column(Text, nullable=False)
    cancel_url = Column(Text, nullable=False)
    
    # Customer is bound at authorization time.
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True, index=True)
    customer = relationship("Customer")
    
    metadata_ = Column("metadata", JSONB, nullable=True, default=dict)

    # Link to actual payment (once confirmed)
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id"), nullable=True, index=True)
    payment = relationship("Payment")

    # Timestamps
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<CheckoutSession {self.id} amount={self.amount_total} status={self.status}>"
