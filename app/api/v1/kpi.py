"""
Internal KPI snapshot endpoints for Composer aggregation.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.checkout_session import CheckoutSession
from app.models.customer import Customer
from app.models.payment import Payment, PaymentStatus

router = APIRouter(prefix="/internal/kpi", tags=["KPI"])


def _status_key(value: PaymentStatus | str | None) -> str:
    if isinstance(value, PaymentStatus):
        return value.value
    if value is None:
        return "unknown"
    return str(value).lower()


@router.get("/snapshot", summary="Payment KPI snapshot")
async def get_kpi_snapshot(db: AsyncSession = Depends(get_db)):
    succeeded_amount = case(
        (Payment.status == PaymentStatus.SUCCEEDED, Payment.amount),
        else_=0,
    )
    pending_amount = case(
        (
            Payment.status.in_(
                [
                    PaymentStatus.PENDING,
                    PaymentStatus.PROCESSING,
                    PaymentStatus.REQUIRES_ACTION,
                ]
            ),
            Payment.amount,
        ),
        else_=0,
    )

    totals_result = await db.execute(
        select(
            func.count(Payment.id),
            func.coalesce(func.sum(Payment.amount), 0),
            func.coalesce(func.sum(succeeded_amount), 0),
            func.coalesce(func.sum(pending_amount), 0),
            func.coalesce(func.sum(Payment.amount_refunded), 0),
        )
    )
    (
        total_payments,
        total_amount_cents,
        total_revenue_cents,
        total_pending_cents,
        total_refunded_cents,
    ) = totals_result.one()

    status_rows = await db.execute(
        select(Payment.status, func.count(Payment.id))
        .group_by(Payment.status)
    )
    by_status = {
        _status_key(status): int(count or 0)
        for status, count in status_rows.all()
    }

    currency_rows = await db.execute(
        select(
            Payment.currency,
            func.count(Payment.id),
            func.coalesce(func.sum(Payment.amount), 0),
            func.coalesce(func.sum(Payment.amount_refunded), 0),
        )
        .group_by(Payment.currency)
    )
    by_currency = {}
    currencies_seen = []
    for currency, count, amount, refunded in currency_rows.all():
        currency_key = str(currency or "eur").upper()
        currencies_seen.append(currency_key)
        by_currency[currency_key] = {
            "payments": int(count or 0),
            "amount_cents": int(amount or 0),
            "refunded_cents": int(refunded or 0),
        }

    customer_total = await db.scalar(select(func.count(Customer.id)))
    customer_active = await db.scalar(
        select(func.count(Customer.id)).where(Customer.is_active.is_(True))
    )

    checkout_rows = await db.execute(
        select(
            CheckoutSession.status,
            func.count(CheckoutSession.id),
            func.coalesce(func.sum(CheckoutSession.amount_total), 0),
        )
        .group_by(CheckoutSession.status)
    )
    checkout_by_status = {}
    checkout_total = 0
    for session_status, count, amount in checkout_rows.all():
        status_key = str(session_status or "unknown").lower()
        checkout_total += int(count or 0)
        checkout_by_status[status_key] = {
            "count": int(count or 0),
            "amount_cents": int(amount or 0),
        }

    return {
        "enabled": True,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "payments": {
            "total_payments": int(total_payments or 0),
            "total_amount_cents": int(total_amount_cents or 0),
            "total_revenue_cents": int(total_revenue_cents or 0),
            "total_pending_cents": int(total_pending_cents or 0),
            "total_refunded_cents": int(total_refunded_cents or 0),
            "currency": currencies_seen[0] if len(set(currencies_seen)) == 1 else "MIXED",
            "by_status": by_status,
            "by_currency": by_currency,
        },
        "customers": {
            "total": int(customer_total or 0),
            "active": int(customer_active or 0),
        },
        "checkout_sessions": {
            "total": checkout_total,
            "by_status": checkout_by_status,
        },
    }
