"""
Payment model — stores payment data for the Digital Wallet system.
"""

import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Enum,
    Text,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class PaymentStatus(str, enum.Enum):
    """Payment lifecycle status."""
    PENDING = "pending"
    PROCESSING = "processing"
    REQUIRES_ACTION = "requires_action"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Relationship to customer
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True, index=True)
    customer = relationship("Customer", back_populates="payments")

    # Payment details
    amount = Column(Integer, nullable=False)          # Amount in smallest currency unit (cents)
    currency = Column(String(3), nullable=False, default="usd")
    status = Column(
        Enum(
            PaymentStatus, 
            name="payment_status",
            values_callable=lambda obj: [e.value for e in obj]
        ),
        nullable=False,
        default=PaymentStatus.PENDING,
        index=True,
    )
    description = Column(Text, nullable=True)

    # Metadata for external systems (e.g., order_id, event_id)
    metadata_ = Column("metadata", JSONB, nullable=True, default=dict)

    # Idempotency
    idempotency_key = Column(String(255), unique=True, nullable=True, index=True)

    # Refund tracking
    amount_refunded = Column(Integer, nullable=False, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    refunds = relationship("Refund", back_populates="payment", lazy="selectin")
    receipt = relationship("Receipt", back_populates="payment", uselist=False, lazy="selectin")

    def __repr__(self) -> str:
        return f"<Payment {self.id} amount={self.amount} status={self.status}>"
