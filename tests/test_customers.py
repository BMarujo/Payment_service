"""
Customer service unit tests.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.customer import Customer
from app.services.customer_service import CustomerService


class TestCustomerService:
    """Unit tests for CustomerService business logic."""

    @pytest.fixture
    def customer_service(self):
        return CustomerService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.fixture
    def sample_customer(self):
        return Customer(
            id=uuid.uuid4(),
            email="test@example.com",
            name="Test User",
            phone="+1234567890",
            metadata_={"type": "vip"},
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    def test_to_response(self, customer_service, sample_customer):
        """Test Customer model to response schema conversion."""
        response = customer_service._to_response(sample_customer)
        assert response.id == sample_customer.id
        assert response.email == "test@example.com"
        assert response.name == "Test User"
        assert response.is_active is True

    @pytest.mark.asyncio
    async def test_get_customer_not_found(self, customer_service, mock_db):
        """Test getting a non-existent customer raises NotFoundError."""
        from app.utils.exceptions import NotFoundError

        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(NotFoundError):
            await customer_service.get_customer(mock_db, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_customer_found(self, customer_service, mock_db, sample_customer):
        """Test getting an existing customer."""
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = sample_customer
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await customer_service.get_customer(mock_db, sample_customer.id)
        assert result.id == sample_customer.id
        assert result.email == "test@example.com"


class TestCustomerModel:
    """Test customer model defaults."""

    def test_customer_defaults(self):
        customer = Customer(
            email="test@example.com",
        )
        assert customer.is_active is True
        assert customer.email == "test@example.com"
