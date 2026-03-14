"""
Checkout session API endpoints.

Provides a hosted payment flow using our custom branded pages — the client
creates a checkout session, gets a local URL, and redirects the end-user there.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import get_settings
from app.models.checkout_session import CheckoutSession
from app.models.payment import Payment, PaymentStatus
from app.models.customer import Customer
from app.schemas.checkout import (
    CheckoutSessionCreate,
    CheckoutSessionResponse,
)
from app.utils.exceptions import NotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/checkout", tags=["Checkout"])


@router.post(
    "/sessions",
    response_model=CheckoutSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a custom checkout session",
    description=(
        "Create a hosted checkout session. Returns a `checkout_url` — "
        "redirect the end-user's browser to that URL to collect payment.\n\n"
        "**This is the main integration point for client services.** "
        "The client only needs to call this endpoint, redirect the user, "
        "and wait for the success redirect."
    ),
)
async def create_checkout_session(
    request: Request,
    data: CheckoutSessionCreate,
    db: AsyncSession = Depends(get_db),
):
    # Calculate total
    amount_total = sum(item.price * item.quantity for item in data.line_items)

    # Convert line items to dicts
    line_items = [item.model_dump() for item in data.line_items]

    # Convert metadata values to strings
    metadata = {}
    if data.metadata:
        metadata = {k: str(v) for k, v in data.metadata.items()}

    # Retrieve or create customer by email
    cust_res = await db.execute(select(Customer).where(Customer.email == data.customer_email))
    customer = cust_res.scalar_one_or_none()
    if not customer:
        customer = Customer(
            email=data.customer_email,
            name=data.customer_name or "Guest User"
        )
        db.add(customer)
        await db.flush()

    # Create local session
    session = CheckoutSession(
        status="open",
        line_items=line_items,
        amount_total=amount_total,
        currency=data.currency.lower(),
        success_url=data.success_url,
        cancel_url=data.cancel_url,
        customer_id=customer.id,
        metadata_=metadata,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    
    db.add(session)
    await db.flush()
    await db.refresh(session)
    
    # Generate local checkout URL
    base_url = str(request.base_url).rstrip("/")
    checkout_url = f"{base_url}/checkout/{session.id}"
    settings = get_settings()

    return CheckoutSessionResponse(
        session_id=str(session.id),
        publishable_key=settings.stripe_publishable_key,
        line_items=data.line_items,
        checkout_url=checkout_url,
        status=session.status,
        success_url=session.success_url,
        cancel_url=session.cancel_url,
        expires_at=session.expires_at,
        payment_status="unpaid",
        amount_total=session.amount_total,
        currency=session.currency,
        customer_name=customer.name or "",
        customer_email=customer.email,
        metadata=session.metadata_,
    )


@router.post(
    "/sessions/{session_id}/pay",
    summary="Process custom checkout payment",
    description="Creates an internal PaymentIntent and returns the client_secret.",
)
async def process_checkout_payment(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    from app.services.payment_service import payment_service
    from app.schemas.payment import PaymentCreate

    result = await db.execute(select(CheckoutSession).where(CheckoutSession.id == session_id))
    session = result.scalar_one_or_none()
    
    if not session:
        raise NotFoundError("CheckoutSession", str(session_id))
    
    if session.status != "open":
        raise ValueError("This checkout session is no longer open.")

    # If the session already created a payment, reuse it
    if session.payment_id:
        payment_res = await db.execute(select(Payment).where(Payment.id == session.payment_id))
        payment = payment_res.scalar_one_or_none()
        if payment:
            return {"client_secret": payment.client_secret}

    # Create the internal payment (which creates the Stripe PaymentIntent)
    payment_req = PaymentCreate(
        amount=session.amount_total,
        currency=session.currency,
        customer_id=session.customer_id,
        confirm=False,
        description=f"Checkout Session: {session.id}",
        metadata={"checkout_session_id": str(session.id), **(session.metadata_ or {})},
    )
    
    # We use a unique idempotency key for this session
    payment_res = await payment_service.create_payment(db, payment_req, idempotency_key=f"cs_{session.id}")
    
    # Link the payment to the session
    session.payment_id = payment_res.id
    db.add(session)
    await db.commit()
    
    return {"client_secret": payment_res.client_secret}


@router.get(
    "/sessions/{session_id}",
    response_model=CheckoutSessionResponse,
    summary="Get checkout session status",
    description=(
        "Check the status of a checkout session. Use this to verify "
        "payment completion after the user is redirected back.\n\n"
        "**Statuses**: `open` (waiting for payment), `complete` (paid), "
        "`expired` (timed out, ~24h)."
    ),
)
async def get_checkout_session(
    request: Request,
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(CheckoutSession)
        .options(selectinload(CheckoutSession.customer))
        .where(CheckoutSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise NotFoundError("CheckoutSession", str(session_id))
        
    payment_status = "unpaid"
    if session.payment_id:
        payment_res = await db.execute(select(Payment).where(Payment.id == session.payment_id))
        payment = payment_res.scalar_one_or_none()
        if payment and payment.status == PaymentStatus.SUCCEEDED:
            payment_status = "paid"
            if session.status == "open":
                session.status = "complete"
                db.add(session)
                await db.commit()

    # Generate local checkout URL
    base_url = str(request.base_url).rstrip("/")
    checkout_url = f"{base_url}/checkout/{session.id}"
    settings = get_settings()

    return CheckoutSessionResponse(
        session_id=str(session.id),
        publishable_key=settings.stripe_publishable_key,
        line_items=session.line_items,
        checkout_url=checkout_url,
        status=session.status,
        success_url=session.success_url,
        cancel_url=session.cancel_url,
        expires_at=session.expires_at,
        payment_status=payment_status,
        amount_total=session.amount_total,
        currency=session.currency,
        customer_name=session.customer.name or "",
        customer_email=session.customer.email,
        metadata=session.metadata_,
    )
