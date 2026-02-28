"""
Customer model — stores customer data synced with Stripe.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    stripe_customer_id = Column(String(255), unique=True, nullable=True, index=True)

    # Customer details
    email = Column(String(255), nullable=False, index=True)
    name = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)

    # Metadata for external systems
    metadata_ = Column("metadata", JSONB, nullable=True, default=dict)

    # Soft delete
    is_active = Column(Boolean, nullable=False, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    payments = relationship("Payment", back_populates="customer", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Customer {self.id} email={self.email}>"
