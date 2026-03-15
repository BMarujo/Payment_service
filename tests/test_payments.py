"""
Payment service unit tests.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.models.payment import Payment, PaymentStatus
from app.schemas.payment import PaymentCreate
from app.services.payment_service import PaymentService


class TestPaymentService:
    """Unit tests for PaymentService business logic."""

    @pytest.fixture
    def payment_service(self):
        return PaymentService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.fixture
    def sample_payment(self):
        return Payment(
            id=uuid.uuid4(),
            amount=5000,
            currency="usd",
            status=PaymentStatus.SUCCEEDED,
            description="Test payment",
            metadata_={"order_id": "123"},
            amount_refunded=0,
            idempotency_key=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    def test_to_response(self, payment_service, sample_payment):
        """Test Payment model to response schema conversion."""
        response = payment_service._to_response(sample_payment)
        assert response.id == sample_payment.id
        assert response.amount == 5000
        assert response.currency == "usd"
        assert response.status == "succeeded"

    @pytest.mark.asyncio
    async def test_get_payment_not_found(self, payment_service, mock_db):
        """Test getting a non-existent payment raises NotFoundError."""
        from app.utils.exceptions import NotFoundError

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(NotFoundError):
            await payment_service.get_payment(mock_db, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_payment_found(self, payment_service, mock_db, sample_payment):
        """Test getting an existing payment."""
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = sample_payment
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await payment_service.get_payment(mock_db, sample_payment.id)
        assert result.id == sample_payment.id
        assert result.amount == 5000

    @pytest.mark.asyncio
    async def test_confirm_already_succeeded(self, payment_service, mock_db, sample_payment):
        """Test confirming an already succeeded payment returns idempotently."""
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = sample_payment
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await payment_service.confirm_payment(mock_db, sample_payment.id)
        assert result.status == "succeeded"


class TestPaymentStatusEnum:
    """Test payment status enum values."""

    def test_all_statuses_exist(self):
        statuses = [s.value for s in PaymentStatus]
        assert "pending" in statuses
        assert "processing" in statuses
        assert "succeeded" in statuses
        assert "failed" in statuses
        assert "canceled" in statuses
        assert "refunded" in statuses
        assert "partially_refunded" in statuses
