"""
Payment API endpoints.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi.responses import Response

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.idempotency import idempotency_service
from app.schemas.payment import PaymentCreate, PaymentResponse, PaymentListResponse
from app.services.payment_service import payment_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post(
    "",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a payment",
    description=(
        "Create a new payment intent via Stripe. Use Stripe test payment methods "
        "like `pm_card_visa` for testing. Supports idempotency via the "
        "`Idempotency-Key` header."
    ),
)
async def create_payment(
    data: PaymentCreate,
    db: AsyncSession = Depends(get_db),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    # Check idempotency cache
    if idempotency_key:
        cached = await idempotency_service.get_cached_response(idempotency_key)
        if cached:
            return cached["body"]

    result = await payment_service.create_payment(
        db=db,
        data=data,
        idempotency_key=idempotency_key,
    )

    # Cache for idempotency
    if idempotency_key:
        await idempotency_service.cache_response(
            idempotency_key, 201, result.model_dump(mode="json")
        )

    return result


@router.get(
    "",
    response_model=PaymentListResponse,
    summary="List payments",
    description="Retrieve a paginated list of payments with optional filters.",
)
async def list_payments(
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    customer_id: Optional[UUID] = Query(None, description="Filter by customer ID"),
    db: AsyncSession = Depends(get_db),
):
    return await payment_service.list_payments(
        db=db,
        limit=limit,
        offset=offset,
        status=status_filter,
        customer_id=customer_id,
    )


@router.get(
    "/{payment_id}",
    response_model=PaymentResponse,
    summary="Get payment details",
    description="Retrieve details of a specific payment by its ID.",
)
async def get_payment(
    payment_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    return await payment_service.get_payment(db=db, payment_id=payment_id)


@router.put(
    "/{payment_id}/confirm",
    response_model=PaymentResponse,
    summary="Confirm a payment",
    description=(
        "Confirm/capture a pending payment intent. Updates the existing payment "
        "status to 'succeeded' (or 'requires_action' if further steps are needed)."
    ),
)
async def confirm_payment(
    payment_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    return await payment_service.confirm_payment(db=db, payment_id=payment_id)


@router.delete(
    "/{payment_id}",
    response_model=PaymentResponse,
    summary="Cancel or refund a payment",
    description=(
        "Cancel or refund a payment depending on its current status:\n\n"
        "- **Pending / processing / requires_action** → cancels the payment via Stripe\n"
        "- **Succeeded** → automatically issues a full refund via Stripe\n\n"
        "The payment status is updated accordingly (`canceled` or `refunded`)."
    ),
)
async def cancel_or_refund_payment(
    payment_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    return await payment_service.cancel_or_refund_payment(db=db, payment_id=payment_id)


@router.get(
    "/{payment_id}/receipt",
    summary="Download payment receipt",
    description="Generate and download a PDF receipt for a succeeded payment.",
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "PDF receipt file",
        }
    },
)
async def download_receipt(
    payment_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    from app.services.receipt_service import receipt_service

    receipt_meta, pdf_data = await receipt_service.get_or_create_receipt(
        db=db, payment_id=payment_id
    )
    return Response(
        content=pdf_data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="receipt-{receipt_meta.receipt_number}.pdf"'
        },
    )
