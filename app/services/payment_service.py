"""
Payment business logic — orchestrates Digital Wallet payments and database operations.
"""

import logging
import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment, PaymentStatus
from app.schemas.payment import PaymentCreate, PaymentResponse, PaymentListResponse
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
        """Create a new payment and persist to DB."""

        # Verify customer exists
        if data.customer_id:
            from app.models.customer import Customer

            result = await db.execute(
                select(Customer).where(Customer.id == data.customer_id)
            )
            customer = result.scalar_one_or_none()
            if not customer:
                raise NotFoundError("Customer", str(data.customer_id))

        # Persist to database — direct payments start as pending (use confirm to succeed)
        payment = Payment(
            customer_id=data.customer_id,
            amount=data.amount,
            currency=data.currency.lower(),
            status=PaymentStatus.PENDING,
            description=data.description,
            metadata_=data.metadata,
            idempotency_key=idempotency_key,
        )
        db.add(payment)
        await db.flush()
        await db.refresh(payment)

        logger.info(f"Payment created: {payment.id} status={payment.status}")
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
        """Confirm a pending payment."""
        payment = await self._get_payment_or_404(db, payment_id)

        # Idempotent: if already succeeded, just return it
        if payment.status == PaymentStatus.SUCCEEDED:
            logger.info(f"Payment {payment.id} already succeeded, returning current state")
            return self._to_response(payment)

        if payment.status not in (PaymentStatus.PENDING, PaymentStatus.REQUIRES_ACTION):
            raise PaymentError(
                f"Cannot confirm payment in '{payment.status.value}' status. "
                f"Only 'pending' or 'requires_action' payments can be confirmed."
            )

        payment.status = PaymentStatus.SUCCEEDED
        await db.flush()
        await db.refresh(payment)

        logger.info(f"Payment confirmed: {payment.id} new_status={payment.status}")
        return self._to_response(payment)

    async def cancel_or_refund_payment(
        self, db: AsyncSession, payment_id: uuid.UUID
    ) -> PaymentResponse:
        """
        Cancel or refund a payment depending on its current status:
        - Pending/processing/requires_action -> cancel
        - Succeeded/partially_refunded -> full refund
        """
        payment = await self._get_payment_or_404(db, payment_id)

        cancelable = (
            PaymentStatus.PENDING,
            PaymentStatus.REQUIRES_ACTION,
            PaymentStatus.PROCESSING,
        )

        if payment.status in cancelable:
            # ── Cancel path ──
            payment.status = PaymentStatus.CANCELED
            logger.info(f"Payment canceled: {payment.id}")

        elif payment.status in (PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED):
            # ── Refund path ──
            refund_amount = payment.amount - payment.amount_refunded
            if refund_amount <= 0:
                raise PaymentError("Payment has already been fully refunded")

            payment.amount_refunded = payment.amount
            payment.status = PaymentStatus.REFUNDED
            logger.info(f"Payment refunded: {payment.id} amount={refund_amount}")

        elif payment.status == PaymentStatus.REFUNDED:
            logger.info(f"Payment {payment.id} already refunded, returning current state")
            return self._to_response(payment)
        elif payment.status == PaymentStatus.CANCELED:
            logger.info(f"Payment {payment.id} already canceled, returning current state")
            return self._to_response(payment)
        else:
            raise PaymentError(
                f"Cannot cancel or refund payment in '{payment.status.value}' status."
            )

        await db.flush()
        await db.refresh(payment)
        return self._to_response(payment)

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
    def _to_response(payment: Payment) -> PaymentResponse:
        return PaymentResponse(
            id=payment.id,
            customer_id=payment.customer_id,
            amount=payment.amount,
            currency=payment.currency,
            status=payment.status.value,
            description=payment.description,
            metadata=payment.metadata_,
            amount_refunded=payment.amount_refunded,
            idempotency_key=payment.idempotency_key,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
        )


# Singleton
payment_service = PaymentService()
