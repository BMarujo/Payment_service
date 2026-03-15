"""
Refund business logic — orchestrates Stripe refund calls and DB operations.
"""

import logging
import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment, PaymentStatus
from app.models.refund import Refund, RefundStatus, RefundReason
from app.schemas.refund import RefundCreate, RefundResponse, RefundListResponse
from app.services.stripe_service import stripe_service
from app.utils.exceptions import NotFoundError, RefundError

logger = logging.getLogger(__name__)


class RefundService:
    """Refund processing business logic."""

    async def create_refund(
        self,
        db: AsyncSession,
        data: RefundCreate,
        idempotency_key: Optional[str] = None,
    ) -> RefundResponse:
        """Create a refund for a payment."""
        # Get the payment
        result = await db.execute(
            select(Payment).where(Payment.id == data.payment_id)
        )
        payment = result.scalar_one_or_none()
        if not payment:
            raise NotFoundError("Payment", str(data.payment_id))

        # Validate payment status
        if payment.status not in (PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED):
            raise RefundError(
                f"Cannot refund payment in '{payment.status.value}' status. "
                f"Only 'succeeded' or 'partially_refunded' payments can be refunded."
            )

        # Calculate refund amount
        refund_amount = data.amount or (payment.amount - payment.amount_refunded)
        if refund_amount <= 0:
            raise RefundError("Refund amount must be greater than zero")

        max_refundable = payment.amount - payment.amount_refunded
        if refund_amount > max_refundable:
            raise RefundError(
                f"Refund amount ({refund_amount}) exceeds maximum refundable amount ({max_refundable})"
            )

        # Map reason enum
        try:
            reason_enum = RefundReason(data.reason)
        except ValueError:
            reason_enum = RefundReason.OTHER

        if not payment.stripe_payment_intent_id:
            # Internal wallet payment — process refund locally without Stripe
            refund = Refund(
                payment_id=data.payment_id,
                amount=refund_amount,
                reason=reason_enum,
                status=RefundStatus.SUCCEEDED,
                description=data.description,
                idempotency_key=idempotency_key,
            )
            db.add(refund)

            payment.amount_refunded += refund_amount
            if payment.amount_refunded >= payment.amount:
                payment.status = PaymentStatus.REFUNDED
            else:
                payment.status = PaymentStatus.PARTIALLY_REFUNDED

            await db.flush()
            await db.refresh(refund)

            logger.info(
                f"Wallet refund created: {refund.id} for payment {data.payment_id} "
                f"amount={refund_amount} status={refund.status}"
            )
            return self._to_response(refund)

        # Map reason for Stripe
        stripe_reason = None
        if data.reason in ("duplicate", "fraudulent", "requested_by_customer"):
            stripe_reason = data.reason

        # Create Stripe refund
        stripe_refund = await stripe_service.create_refund(
            payment_intent_id=payment.stripe_payment_intent_id,
            amount=refund_amount,
            reason=stripe_reason,
            idempotency_key=idempotency_key,
        )

        # Persist refund
        refund = Refund(
            stripe_refund_id=stripe_refund.id,
            payment_id=data.payment_id,
            amount=refund_amount,
            reason=reason_enum,
            status=RefundStatus.SUCCEEDED if stripe_refund.status == "succeeded" else RefundStatus.PENDING,
            description=data.description,
            idempotency_key=idempotency_key,
        )
        db.add(refund)

        # Update payment refund tracking
        payment.amount_refunded += refund_amount
        if payment.amount_refunded >= payment.amount:
            payment.status = PaymentStatus.REFUNDED
        else:
            payment.status = PaymentStatus.PARTIALLY_REFUNDED

        await db.flush()
        await db.refresh(refund)

        logger.info(
            f"Refund created: {refund.id} for payment {data.payment_id} "
            f"amount={refund_amount} status={refund.status}"
        )
        return self._to_response(refund)

    async def get_refund(self, db: AsyncSession, refund_id: uuid.UUID) -> RefundResponse:
        """Get a single refund by ID."""
        refund = await self._get_refund_or_404(db, refund_id)
        return self._to_response(refund)

    async def list_refunds(
        self,
        db: AsyncSession,
        limit: int = 20,
        offset: int = 0,
        payment_id: Optional[uuid.UUID] = None,
    ) -> RefundListResponse:
        """List refunds with pagination and optional filters."""
        query = select(Refund)

        if payment_id:
            query = query.where(Refund.payment_id == payment_id)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar_one()

        # Fetch page
        query = query.order_by(Refund.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(query)
        refunds = result.scalars().all()

        return RefundListResponse(
            items=[self._to_response(r) for r in refunds],
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < total,
        )

    # ── Helpers ───────────────────────────────────────

    async def _get_refund_or_404(
        self, db: AsyncSession, refund_id: uuid.UUID
    ) -> Refund:
        result = await db.execute(select(Refund).where(Refund.id == refund_id))
        refund = result.scalar_one_or_none()
        if not refund:
            raise NotFoundError("Refund", str(refund_id))
        return refund

    @staticmethod
    def _to_response(refund: Refund) -> RefundResponse:
        return RefundResponse(
            id=refund.id,
            stripe_refund_id=refund.stripe_refund_id,
            payment_id=refund.payment_id,
            amount=refund.amount,
            reason=refund.reason.value,
            status=refund.status.value,
            description=refund.description,
            idempotency_key=refund.idempotency_key,
            created_at=refund.created_at,
            updated_at=refund.updated_at,
        )


# Singleton
refund_service = RefundService()
