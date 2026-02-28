"""
Refund API endpoints.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.idempotency import idempotency_service
from app.schemas.refund import RefundCreate, RefundResponse, RefundListResponse
from app.services.refund_service import refund_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/refunds", tags=["Refunds"])


@router.post(
    "",
    response_model=RefundResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a refund",
    description=(
        "Create a refund for a succeeded payment. Supports partial refunds "
        "by specifying an amount less than the original payment. "
        "Supports idempotency via the `Idempotency-Key` header."
    ),
)
async def create_refund(
    data: RefundCreate,
    db: AsyncSession = Depends(get_db),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    # Check idempotency cache
    if idempotency_key:
        cached = await idempotency_service.get_cached_response(idempotency_key)
        if cached:
            return cached["body"]

    result = await refund_service.create_refund(
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
    response_model=RefundListResponse,
    summary="List refunds",
    description="Retrieve a paginated list of refunds with optional filters.",
)
async def list_refunds(
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    payment_id: Optional[UUID] = Query(None, description="Filter by payment ID"),
    db: AsyncSession = Depends(get_db),
):
    return await refund_service.list_refunds(
        db=db,
        limit=limit,
        offset=offset,
        payment_id=payment_id,
    )


@router.get(
    "/{refund_id}",
    response_model=RefundResponse,
    summary="Get refund details",
    description="Retrieve details of a specific refund by its ID.",
)
async def get_refund(
    refund_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    return await refund_service.get_refund(db=db, refund_id=refund_id)
