"""
Webhook handler tests.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.services.stripe_service import StripeService


class TestStripeService:
    """Unit tests for StripeService."""

    @pytest.fixture
    def stripe_service(self):
        return StripeService()

    def test_verify_webhook_valid(self, stripe_service, mock_stripe):
        """Test webhook verification with valid signature."""
        mock_event = {
            "id": "evt_test_123",
            "type": "payment_intent.succeeded",
            "data": {"object": {"id": "pi_test_123", "status": "succeeded"}},
        }
        mock_stripe.Webhook.construct_event.return_value = mock_event

        result = stripe_service.verify_webhook_signature(b"payload", "sig_header")
        assert result["type"] == "payment_intent.succeeded"

    def test_verify_webhook_invalid_signature(self, stripe_service, mock_stripe):
        """Test webhook verification with invalid signature raises error."""
        from app.utils.exceptions import StripeError

        mock_stripe.Webhook.construct_event.side_effect = (
            mock_stripe.SignatureVerificationError("bad sig")
        )

        with pytest.raises(StripeError):
            stripe_service.verify_webhook_signature(b"payload", "bad_sig")


class TestStripePaymentIntentMethods:
    """Test Stripe PaymentIntent wrapper methods."""

    @pytest.fixture
    def stripe_service(self):
        return StripeService()

    @pytest.mark.asyncio
    async def test_create_payment_intent(self, stripe_service, mock_stripe):
        """Test creating a payment intent."""
        result = await stripe_service.create_payment_intent(
            amount=5000,
            currency="usd",
            description="Test",
        )
        assert result.id == "pi_test_123"
        mock_stripe.PaymentIntent.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_retrieve_payment_intent(self, stripe_service, mock_stripe):
        """Test retrieving a payment intent."""
        result = await stripe_service.retrieve_payment_intent("pi_test_123")
        assert result.id == "pi_test_123"

    @pytest.mark.asyncio
    async def test_cancel_payment_intent(self, stripe_service, mock_stripe):
        """Test canceling a payment intent."""
        result = await stripe_service.cancel_payment_intent("pi_test_123")
        assert result.status == "canceled"
