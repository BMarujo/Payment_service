"""
Stripe SDK wrapper — thin abstraction over the Stripe Python library.

All Stripe API interactions go through this module, making it easy to
mock in tests and swap providers in the future.
"""

import logging
from typing import Any, Dict, Optional

import stripe

from app.config import get_settings
from app.utils.exceptions import StripeError

logger = logging.getLogger(__name__)


class StripeService:
    """Wrapper around the Stripe Python SDK."""

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.stripe_secret_key
        self._webhook_secret = settings.stripe_webhook_secret
        stripe.api_key = self._api_key

    # ── Payment Intents ──────────────────────────────

    async def create_payment_intent(
        self,
        amount: int,
        currency: str,
        customer_id: Optional[str] = None,
        payment_method_id: Optional[str] = None,
        confirm: bool = True,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> stripe.PaymentIntent:
        """Create a Stripe PaymentIntent."""
        try:
            params: Dict[str, Any] = {
                "amount": amount,
                "currency": currency,
                "automatic_payment_methods": {"enabled": True, "allow_redirects": "never"},
                "description": description,
                "metadata": metadata or {},
            }

            if customer_id:
                params["customer"] = customer_id
            if payment_method_id:
                params["payment_method"] = payment_method_id
            if confirm:
                params["confirm"] = True

            kwargs: Dict[str, Any] = {}
            if idempotency_key:
                kwargs["idempotency_key"] = idempotency_key

            intent = stripe.PaymentIntent.create(**params, **kwargs)
            logger.info(f"Created PaymentIntent: {intent.id} status={intent.status}")
            return intent

        except stripe.StripeError as e:
            logger.error(f"Stripe error creating PaymentIntent: {e}")
            raise StripeError(detail=str(e.user_message or e))

    async def retrieve_payment_intent(self, payment_intent_id: str) -> stripe.PaymentIntent:
        """Retrieve a PaymentIntent from Stripe."""
        try:
            return stripe.PaymentIntent.retrieve(payment_intent_id)
        except stripe.StripeError as e:
            logger.error(f"Stripe error retrieving PaymentIntent: {e}")
            raise StripeError(detail=str(e.user_message or e))

    async def confirm_payment_intent(self, payment_intent_id: str) -> stripe.PaymentIntent:
        """Confirm a PaymentIntent."""
        try:
            intent = stripe.PaymentIntent.confirm(payment_intent_id)
            logger.info(f"Confirmed PaymentIntent: {intent.id} status={intent.status}")
            return intent
        except stripe.StripeError as e:
            logger.error(f"Stripe error confirming PaymentIntent: {e}")
            raise StripeError(detail=str(e.user_message or e))

    async def cancel_payment_intent(self, payment_intent_id: str) -> stripe.PaymentIntent:
        """Cancel a PaymentIntent."""
        try:
            intent = stripe.PaymentIntent.cancel(payment_intent_id)
            logger.info(f"Canceled PaymentIntent: {intent.id}")
            return intent
        except stripe.StripeError as e:
            logger.error(f"Stripe error canceling PaymentIntent: {e}")
            raise StripeError(detail=str(e.user_message or e))

    # ── Refunds ──────────────────────────────────────

    async def create_refund(
        self,
        payment_intent_id: str,
        amount: Optional[int] = None,
        reason: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> stripe.Refund:
        """Create a Stripe Refund."""
        try:
            params: Dict[str, Any] = {"payment_intent": payment_intent_id}
            if amount is not None:
                params["amount"] = amount
            if reason:
                params["reason"] = reason

            kwargs: Dict[str, Any] = {}
            if idempotency_key:
                kwargs["idempotency_key"] = idempotency_key

            refund = stripe.Refund.create(**params, **kwargs)
            logger.info(f"Created Refund: {refund.id} status={refund.status}")
            return refund

        except stripe.StripeError as e:
            logger.error(f"Stripe error creating Refund: {e}")
            raise StripeError(detail=str(e.user_message or e))

    # ── Customers ────────────────────────────────────

    async def create_customer(
        self,
        email: str,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> stripe.Customer:
        """Create a Stripe Customer."""
        try:
            params: Dict[str, Any] = {"email": email, "metadata": metadata or {}}
            if name:
                params["name"] = name
            if phone:
                params["phone"] = phone

            customer = stripe.Customer.create(**params)
            logger.info(f"Created Stripe Customer: {customer.id}")
            return customer

        except stripe.StripeError as e:
            logger.error(f"Stripe error creating Customer: {e}")
            raise StripeError(detail=str(e.user_message or e))

    async def update_customer(
        self,
        customer_id: str,
        **kwargs: Any,
    ) -> stripe.Customer:
        """Update a Stripe Customer."""
        try:
            customer = stripe.Customer.modify(customer_id, **kwargs)
            logger.info(f"Updated Stripe Customer: {customer.id}")
            return customer
        except stripe.StripeError as e:
            logger.error(f"Stripe error updating Customer: {e}")
            raise StripeError(detail=str(e.user_message or e))

    async def delete_customer(self, customer_id: str) -> None:
        """Delete a Stripe Customer."""
        try:
            stripe.Customer.delete(customer_id)
            logger.info(f"Deleted Stripe Customer: {customer_id}")
        except stripe.StripeError as e:
            logger.error(f"Stripe error deleting Customer: {e}")
            raise StripeError(detail=str(e.user_message or e))

    # ── Webhooks ─────────────────────────────────────

    def verify_webhook_signature(self, payload: bytes, sig_header: str) -> dict:
        """Verify and parse a Stripe webhook event."""
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, self._webhook_secret
            )
            logger.info(f"Verified webhook event: {event['type']} id={event['id']}")
            return event
        except stripe.SignatureVerificationError as e:
            logger.error(f"Webhook signature verification failed: {e}")
            raise StripeError(detail="Invalid webhook signature", status_code=400)
        except ValueError as e:
            logger.error(f"Invalid webhook payload: {e}")
            raise StripeError(detail="Invalid webhook payload", status_code=400)


# Singleton
stripe_service = StripeService()
