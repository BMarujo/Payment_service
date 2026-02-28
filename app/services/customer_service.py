"""
Customer business logic — manages customers both locally and in Stripe.
"""

import logging
import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.schemas.customer import (
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    CustomerListResponse,
)
from app.services.stripe_service import stripe_service
from app.utils.exceptions import NotFoundError

logger = logging.getLogger(__name__)


class CustomerService:
    """Customer management business logic."""

    async def create_customer(
        self, db: AsyncSession, data: CustomerCreate
    ) -> CustomerResponse:
        """Create a customer locally and in Stripe."""
        # Convert metadata values to strings for Stripe
        stripe_metadata = {}
        if data.metadata:
            stripe_metadata = {k: str(v) for k, v in data.metadata.items()}

        # Create in Stripe
        stripe_customer = await stripe_service.create_customer(
            email=data.email,
            name=data.name,
            phone=data.phone,
            metadata=stripe_metadata,
        )

        # Persist locally
        customer = Customer(
            stripe_customer_id=stripe_customer.id,
            email=data.email,
            name=data.name,
            phone=data.phone,
            metadata_=data.metadata,
        )
        db.add(customer)
        await db.flush()
        await db.refresh(customer)

        logger.info(f"Customer created: {customer.id} stripe_id={stripe_customer.id}")
        return self._to_response(customer)

    async def get_customer(
        self, db: AsyncSession, customer_id: uuid.UUID
    ) -> CustomerResponse:
        """Get a single customer by ID."""
        customer = await self._get_customer_or_404(db, customer_id)
        return self._to_response(customer)

    async def list_customers(
        self,
        db: AsyncSession,
        limit: int = 20,
        offset: int = 0,
        email: Optional[str] = None,
    ) -> CustomerListResponse:
        """List customers with pagination."""
        query = select(Customer).where(Customer.is_active == True)  # noqa: E712

        if email:
            query = query.where(Customer.email.ilike(f"%{email}%"))

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar_one()

        # Fetch page
        query = query.order_by(Customer.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(query)
        customers = result.scalars().all()

        return CustomerListResponse(
            items=[self._to_response(c) for c in customers],
            total=total,
            limit=limit,
            offset=offset,
            has_more=(offset + limit) < total,
        )

    async def update_customer(
        self, db: AsyncSession, customer_id: uuid.UUID, data: CustomerUpdate
    ) -> CustomerResponse:
        """Update a customer locally and in Stripe."""
        customer = await self._get_customer_or_404(db, customer_id)

        # Build update params
        update_data = data.model_dump(exclude_unset=True)

        # Update in Stripe
        if customer.stripe_customer_id and update_data:
            stripe_params = {}
            if "email" in update_data:
                stripe_params["email"] = update_data["email"]
            if "name" in update_data:
                stripe_params["name"] = update_data["name"]
            if "phone" in update_data:
                stripe_params["phone"] = update_data["phone"]
            if "metadata" in update_data and update_data["metadata"]:
                stripe_params["metadata"] = {
                    k: str(v) for k, v in update_data["metadata"].items()
                }

            if stripe_params:
                await stripe_service.update_customer(
                    customer.stripe_customer_id, **stripe_params
                )

        # Update locally
        for key, value in update_data.items():
            if key == "metadata":
                setattr(customer, "metadata_", value)
            else:
                setattr(customer, key, value)

        await db.flush()
        await db.refresh(customer)

        logger.info(f"Customer updated: {customer.id}")
        return self._to_response(customer)

    async def delete_customer(
        self, db: AsyncSession, customer_id: uuid.UUID
    ) -> None:
        """Soft-delete a customer (and delete from Stripe)."""
        customer = await self._get_customer_or_404(db, customer_id)

        # Delete from Stripe
        if customer.stripe_customer_id:
            await stripe_service.delete_customer(customer.stripe_customer_id)

        # Soft delete locally
        customer.is_active = False
        await db.flush()

        logger.info(f"Customer deleted (soft): {customer.id}")

    # ── Helpers ───────────────────────────────────────

    async def _get_customer_or_404(
        self, db: AsyncSession, customer_id: uuid.UUID
    ) -> Customer:
        result = await db.execute(
            select(Customer).where(
                Customer.id == customer_id, Customer.is_active == True  # noqa: E712
            )
        )
        customer = result.scalar_one_or_none()
        if not customer:
            raise NotFoundError("Customer", str(customer_id))
        return customer

    @staticmethod
    def _to_response(customer: Customer) -> CustomerResponse:
        return CustomerResponse(
            id=customer.id,
            stripe_customer_id=customer.stripe_customer_id,
            email=customer.email,
            name=customer.name,
            phone=customer.phone,
            metadata=customer.metadata_,
            is_active=customer.is_active,
            created_at=customer.created_at,
            updated_at=customer.updated_at,
        )


# Singleton
customer_service = CustomerService()
