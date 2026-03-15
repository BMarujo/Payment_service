"""
Refund model — stores refund data for the Digital Wallet system.
"""

import uuid
import enum
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, DateTime, Enum, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class RefundStatus(str, enum.Enum):
    """Refund lifecycle status."""
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


class RefundReason(str, enum.Enum):
    """Standard refund reasons."""
    DUPLICATE = "duplicate"
    FRAUDULENT = "fraudulent"
    REQUESTED_BY_CUSTOMER = "requested_by_customer"
    OTHER = "other"


class Refund(Base):
    __tablename__ = "refunds"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Relationship to payment
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id"), nullable=False, index=True)
    payment = relationship("Payment", back_populates="refunds")

    # Refund details
    amount = Column(Integer, nullable=False)  # Amount in smallest currency unit
    reason = Column(
        Enum(
            RefundReason,
            name="refund_reason",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=RefundReason.REQUESTED_BY_CUSTOMER,
    )
    status = Column(
        Enum(
            RefundStatus,
            name="refund_status",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=RefundStatus.PENDING,
        index=True,
    )
    description = Column(Text, nullable=True)

    # Idempotency
    idempotency_key = Column(String(255), unique=True, nullable=True, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<Refund {self.id} amount={self.amount} status={self.status}>"
