"""
Test fixtures and configuration.
"""

import asyncio
import os
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Set test environment before importing app modules
os.environ["ENVIRONMENT"] = "test"
os.environ["API_KEY"] = "test-api-key"
os.environ["STRIPE_SECRET_KEY"] = "sk_test_fake"
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_fake"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///test.db"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def api_key_header():
    """Standard auth header for tests."""
    return {"X-API-Key": "test-api-key"}


@pytest.fixture
def mock_stripe():
    """Mock all Stripe API calls."""
    with patch("app.services.stripe_service.stripe") as mock_stripe_module:
        # Mock PaymentIntent
        mock_intent = MagicMock()
        mock_intent.id = "pi_test_123"
        mock_intent.status = "succeeded"
        mock_intent.client_secret = "pi_test_123_secret_abc"
        mock_stripe_module.PaymentIntent.create.return_value = mock_intent
        mock_stripe_module.PaymentIntent.retrieve.return_value = mock_intent
        mock_stripe_module.PaymentIntent.confirm.return_value = mock_intent
        mock_intent_canceled = MagicMock()
        mock_intent_canceled.id = "pi_test_123"
        mock_intent_canceled.status = "canceled"
        mock_stripe_module.PaymentIntent.cancel.return_value = mock_intent_canceled

        # Mock Refund
        mock_refund = MagicMock()
        mock_refund.id = "re_test_123"
        mock_refund.status = "succeeded"
        mock_stripe_module.Refund.create.return_value = mock_refund

        # Mock Customer
        mock_customer = MagicMock()
        mock_customer.id = "cus_test_123"
        mock_stripe_module.Customer.create.return_value = mock_customer
        mock_stripe_module.Customer.modify.return_value = mock_customer
        mock_stripe_module.Customer.delete.return_value = None

        # Mock errors
        mock_stripe_module.StripeError = Exception
        mock_stripe_module.SignatureVerificationError = Exception

        yield mock_stripe_module


@pytest.fixture
def mock_redis():
    """Mock Redis for idempotency and rate limiting."""
    with patch("app.middleware.idempotency.redis") as mock_idem_redis, \
         patch("app.middleware.rate_limiter.redis") as mock_rate_redis:

        # Idempotency mock
        mock_idem_instance = AsyncMock()
        mock_idem_instance.get.return_value = None
        mock_idem_instance.set.return_value = True
        mock_idem_redis.from_url.return_value = mock_idem_instance

        # Rate limiter — always allow
        mock_rate_instance = AsyncMock()
        mock_pipe = AsyncMock()
        mock_pipe.execute.return_value = [None, None, 1, None]
        mock_rate_instance.pipeline.return_value = mock_pipe
        mock_rate_redis.from_url.return_value = mock_rate_instance

        yield {
            "idempotency": mock_idem_instance,
            "rate_limiter": mock_rate_instance,
        }
