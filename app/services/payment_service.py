"""
Payment business logic — orchestrates Stripe calls and database operations.
"""

import logging
import uuid
from typing import Any, Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment, PaymentStatus
from app.schemas.payment import PaymentCreate, PaymentResponse, PaymentListResponse
from app.services.stripe_service import stripe_service
from app.utils.exceptions import NotFoundError, PaymentError

logger = logging.getLogger(__name__)


class PaymentService:
    """Payment processing business logic."""

    async def create_payment(
        self,
        db: AsyncSession,
        data: PaymentCreate,
        idempotency_key: Optional[str] = None,
    ) -> PaymentResponse:
        """Create a new payment, sync with Stripe, and persist to DB."""

        # Look up Stripe customer ID if customer_id provided
        stripe_customer_id = None
        if data.customer_id:
            from app.models.customer import Customer

            result = await db.execute(
                select(Customer).where(Customer.id == data.customer_id)
            )
            customer = result.scalar_one_or_none()
            if not customer:
                raise NotFoundError("Customer", str(data.customer_id))
            stripe_customer_id = customer.stripe_customer_id

        # Convert metadata values to strings for Stripe
        stripe_metadata = {}
        if data.metadata:
            stripe_metadata = {k: str(v) for k, v in data.metadata.items()}

        # Create Stripe PaymentIntent
        try:
            intent = await stripe_service.create_payment_intent(
                amount=data.amount,
                currency=data.currency.lower(),
                customer_id=stripe_customer_id,
                payment_method_id=data.payment_method_id,
                confirm=data.confirm,
                description=data.description,
                metadata=stripe_metadata,
                idempotency_key=idempotency_key,
            )
        except Exception as e:
            logger.error(f"Failed to create Stripe PaymentIntent: {e}")
            raise

        # Map Stripe status to our status enum
        status = self._map_stripe_status(intent.status)

        # Persist to database
        payment = Payment(
            stripe_payment_intent_id=intent.id,
            customer_id=data.customer_id,
            amount=data.amount,
            currency=data.currency.lower(),
            status=status,
            description=data.description,
            payment_method_id=data.payment_method_id,
            client_secret=intent.client_secret,
            metadata_=data.metadata,
            idempotency_key=idempotency_key,
        )
        db.add(payment)
        await db.flush()
        await db.refresh(payment)

        logger.info(f"Payment created: {payment.id} stripe_id={intent.id} status={status}")
        return self._to_response(payment)

    async def get_payment(self, db: AsyncSession, payment_id: uuid.UUID) -> PaymentResponse:
        """Get a single payment by ID."""
        payment = await self._get_payment_or_404(db, payment_id)
        return self._to_response(payment)

    async def list_payments(
        self,
        db: AsyncSession,
        limit: int = 20,
        offset: int = 0,
        status: Optional[str] = None,
        customer_id: Optional[uuid.UUID] = None,
    ) -> PaymentListResponse:
        """List payments with pagination and optional filters."""
        query = select(Payment)

        if status:
            query = query.where(Payment.status == status)
        if customer_id:
            query = query.where(Payment.customer_id == customer_id)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar_one()

        # Fetch page
        query = query.order_by(Payment.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(query)
        payments = result.scalars().all()

        return PaymentListResponse(
            items=[self._to_response(p) for p in payments],
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < total,
        )

    async def confirm_payment(
        self, db: AsyncSession, payment_id: uuid.UUID
    ) -> PaymentResponse:
        """Confirm/capture a pending payment."""
        payment = await self._get_payment_or_404(db, payment_id)

        # Idempotent: if already succeeded (e.g. webhook beat us), just return it
        if payment.status == PaymentStatus.SUCCEEDED:
            logger.info(f"Payment {payment.id} already succeeded, returning current state")
            return self._to_response(payment)

        if payment.status not in (PaymentStatus.PENDING, PaymentStatus.REQUIRES_ACTION):
            raise PaymentError(
                f"Cannot confirm payment in '{payment.status.value}' status. "
                f"Only 'pending' or 'requires_action' payments can be confirmed."
            )

        if not payment.stripe_payment_intent_id:
            raise PaymentError("Payment has no associated Stripe PaymentIntent")

        intent = await stripe_service.confirm_payment_intent(
            payment.stripe_payment_intent_id
        )
        payment.status = self._map_stripe_status(intent.status)
        await db.flush()
        await db.refresh(payment)

        logger.info(f"Payment confirmed: {payment.id} new_status={payment.status}")
        return self._to_response(payment)

    async def cancel_or_refund_payment(
        self, db: AsyncSession, payment_id: uuid.UUID
    ) -> PaymentResponse:
        """
        Cancel or refund a payment depending on its current status:
        - Pending/processing/requires_action → cancel via Stripe
        - Succeeded → full refund via Stripe
        """
        payment = await self._get_payment_or_404(db, payment_id)

        cancelable = (
            PaymentStatus.PENDING,
            PaymentStatus.REQUIRES_ACTION,
            PaymentStatus.PROCESSING,
        )

        if payment.status in cancelable:
            # ── Cancel path ──
            if payment.stripe_payment_intent_id:
                await stripe_service.cancel_payment_intent(
                    payment.stripe_payment_intent_id
                )
            payment.status = PaymentStatus.CANCELED
            logger.info(f"Payment canceled: {payment.id}")

        elif payment.status == PaymentStatus.SUCCEEDED:
            # ── Refund path ──
            if not payment.stripe_payment_intent_id:
                raise PaymentError("Payment has no associated Stripe PaymentIntent")

            refund_amount = payment.amount - payment.amount_refunded
            if refund_amount <= 0:
                raise PaymentError("Payment has already been fully refunded")

            await stripe_service.create_refund(
                payment_intent_id=payment.stripe_payment_intent_id,
                amount=refund_amount,
                reason="requested_by_customer",
            )

            payment.amount_refunded = payment.amount
            payment.status = PaymentStatus.REFUNDED
            logger.info(f"Payment refunded: {payment.id} amount={refund_amount}")

        elif payment.status in (PaymentStatus.REFUNDED, PaymentStatus.PARTIALLY_REFUNDED):
            # Idempotent: already refunded, just return current state
            logger.info(f"Payment {payment.id} already refunded, returning current state")
            return self._to_response(payment)
        elif payment.status == PaymentStatus.CANCELED:
            # Idempotent: already canceled, just return current state
            logger.info(f"Payment {payment.id} already canceled, returning current state")
            return self._to_response(payment)
        else:
            raise PaymentError(
                f"Cannot cancel or refund payment in '{payment.status.value}' status."
            )

        await db.flush()
        await db.refresh(payment)
        return self._to_response(payment)

    async def update_payment_from_webhook(
        self, db: AsyncSession, stripe_payment_intent_id: str, stripe_status: str
    ) -> Optional[Payment]:
        """Update local payment record from a Stripe webhook event."""
        result = await db.execute(
            select(Payment).where(
                Payment.stripe_payment_intent_id == stripe_payment_intent_id
            )
        )
        payment = result.scalar_one_or_none()
        if not payment:
            logger.warning(
                f"Webhook: PaymentIntent {stripe_payment_intent_id} not found locally"
            )
            return None

        payment.status = self._map_stripe_status(stripe_status)
        await db.flush()
        logger.info(
            f"Webhook updated payment {payment.id} to status={payment.status}"
        )
        return payment

    # ── Helpers ───────────────────────────────────────

    async def _get_payment_or_404(
        self, db: AsyncSession, payment_id: uuid.UUID
    ) -> Payment:
        result = await db.execute(select(Payment).where(Payment.id == payment_id))
        payment = result.scalar_one_or_none()
        if not payment:
            raise NotFoundError("Payment", str(payment_id))
        return payment

    @staticmethod
    def _map_stripe_status(stripe_status: str) -> PaymentStatus:
        mapping = {
            "requires_payment_method": PaymentStatus.PENDING,
            "requires_confirmation": PaymentStatus.PENDING,
            "requires_action": PaymentStatus.REQUIRES_ACTION,
            "processing": PaymentStatus.PROCESSING,
            "succeeded": PaymentStatus.SUCCEEDED,
            "canceled": PaymentStatus.CANCELED,
            "requires_capture": PaymentStatus.PROCESSING,
        }
        return mapping.get(stripe_status, PaymentStatus.FAILED)

    @staticmethod
    def _to_response(payment: Payment) -> PaymentResponse:
        return PaymentResponse(
            id=payment.id,
            stripe_payment_intent_id=payment.stripe_payment_intent_id,
            customer_id=payment.customer_id,
            amount=payment.amount,
            currency=payment.currency,
            status=payment.status.value,
            description=payment.description,
            payment_method_id=payment.payment_method_id,
            client_secret=payment.client_secret,
            metadata=payment.metadata_,
            amount_refunded=payment.amount_refunded,
            idempotency_key=payment.idempotency_key,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
        )


# Singleton
payment_service = PaymentService()
