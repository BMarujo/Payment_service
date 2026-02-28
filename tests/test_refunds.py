"""
Refund service unit tests.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.payment import Payment, PaymentStatus
from app.models.refund import Refund, RefundStatus, RefundReason
from app.services.refund_service import RefundService


class TestRefundService:
    """Unit tests for RefundService business logic."""

    @pytest.fixture
    def refund_service(self):
        return RefundService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.fixture
    def succeeded_payment(self):
        return Payment(
            id=uuid.uuid4(),
            stripe_payment_intent_id="pi_test_456",
            amount=10000,
            currency="usd",
            status=PaymentStatus.SUCCEEDED,
            amount_refunded=0,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def sample_refund(self):
        return Refund(
            id=uuid.uuid4(),
            stripe_refund_id="re_test_123",
            payment_id=uuid.uuid4(),
            amount=5000,
            reason=RefundReason.REQUESTED_BY_CUSTOMER,
            status=RefundStatus.SUCCEEDED,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    def test_to_response(self, refund_service, sample_refund):
        """Test Refund model to response schema conversion."""
        response = refund_service._to_response(sample_refund)
        assert response.id == sample_refund.id
        assert response.amount == 5000
        assert response.reason == "requested_by_customer"
        assert response.status == "succeeded"

    @pytest.mark.asyncio
    async def test_get_refund_not_found(self, refund_service, mock_db):
        """Test getting a non-existent refund raises NotFoundError."""
        from app.utils.exceptions import NotFoundError

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(NotFoundError):
            await refund_service.get_refund(mock_db, uuid.uuid4())


class TestRefundEnums:
    """Test refund enum values."""

    def test_refund_statuses(self):
        statuses = [s.value for s in RefundStatus]
        assert "pending" in statuses
        assert "succeeded" in statuses
        assert "failed" in statuses

    def test_refund_reasons(self):
        reasons = [r.value for r in RefundReason]
        assert "duplicate" in reasons
        assert "fraudulent" in reasons
        assert "requested_by_customer" in reasons
        assert "other" in reasons
