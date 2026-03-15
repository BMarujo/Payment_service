"""
Customer API endpoints.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.customer import (
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    CustomerListResponse,
)
from app.schemas.payment import PaymentListResponse, PaymentResponse
from app.models.payment import Payment
from app.models.customer import Customer
from app.api.deps import get_current_customer
from sqlalchemy.future import select
from sqlalchemy import func
from app.services.customer_service import customer_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/customers", tags=["Customers"])


@router.post(
    "",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a customer",
    description="Create a new customer in the system.",
)
async def create_customer(
    data: CustomerCreate,
    db: AsyncSession = Depends(get_db),
):
    return await customer_service.create_customer(db=db, data=data)


@router.get(
    "",
    response_model=CustomerListResponse,
    summary="List customers",
    description="Retrieve a paginated list of customers.",
)
async def list_customers(
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    email: Optional[str] = Query(None, description="Filter by email (partial match)"),
    db: AsyncSession = Depends(get_db),
):
    return await customer_service.list_customers(
        db=db,
        limit=limit,
        offset=offset,
        email=email,
    )


@router.get(
    "/me/transactions",
    response_model=PaymentListResponse,
    summary="Get my transactions",
    description="Retrieve the payment history for the currently authenticated customer.",
)
async def get_my_transactions(
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    current_customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Payment)
        .where(Payment.customer_id == current_customer.id)
        .order_by(Payment.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    payments = result.scalars().all()

    count_res = await db.execute(
        select(func.count(Payment.id)).where(Payment.customer_id == current_customer.id)
    )
    total = count_res.scalar_one()

    items = [
        PaymentResponse(
            id=p.id,
            customer_id=p.customer_id,
            amount=p.amount,
            currency=p.currency,
            status=p.status.value,
            description=p.description,
            metadata=p.metadata_,
            amount_refunded=p.amount_refunded,
            idempotency_key=p.idempotency_key,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in payments
    ]
    return PaymentListResponse(items=items, total=total, limit=limit, offset=offset, has_more=(offset + limit) < total)


@router.get(
    "/{customer_id}",
    response_model=CustomerResponse,
    summary="Get customer details",
    description="Retrieve details of a specific customer by ID.",
)
async def get_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    return await customer_service.get_customer(db=db, customer_id=customer_id)


@router.put(
    "/{customer_id}",
    response_model=CustomerResponse,
    summary="Update a customer",
    description="Update customer details. Only provided fields will be changed.",
)
async def update_customer(
    customer_id: UUID,
    data: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
):
    return await customer_service.update_customer(
        db=db, customer_id=customer_id, data=data
    )


@router.delete(
    "/{customer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a customer",
    description="Soft-delete a customer.",
)
async def delete_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    await customer_service.delete_customer(db=db, customer_id=customer_id)
    return None
