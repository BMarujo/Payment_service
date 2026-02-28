"""
Receipt model — stores generated PDF receipts for successful payments.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, ForeignKey, LargeBinary
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class Receipt(Base):
    __tablename__ = "receipts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Relationship to payment
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id"), nullable=False, unique=True, index=True)
    payment = relationship("Payment", back_populates="receipt")

    # Receipt details
    receipt_number = Column(String(50), unique=True, nullable=False, index=True)

    # PDF binary data
    pdf_data = Column(LargeBinary, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<Receipt {self.receipt_number} payment_id={self.payment_id}>"
