"""
Checkout session API endpoints.

Provides a hosted payment flow using our custom branded pages — the client
creates a checkout session, gets a local URL, and redirects the end-user there.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, status, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.checkout_session import CheckoutSession
from app.models.payment import Payment, PaymentStatus
from app.models.customer import Customer
from app.schemas.checkout import (
    CheckoutSessionCreate,
    CheckoutSessionResponse,
    CheckoutAuthorizeResponse,
)
from app.utils.exceptions import NotFoundError, PaymentError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/checkout", tags=["Checkout"])


@router.post(
    "",
    response_model=CheckoutSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a custom checkout session",
    description=(
        "Create a hosted checkout session. Returns a `checkout_url` — "
        "redirect the end-user's browser to that URL to collect their custom Digital Wallet authorization.\n\n"
        "**This is the main integration point for client services.** "
        "The client only needs to call this endpoint, redirect the user to the local UI, "
        "and wait for the success callback redirect."
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

    # Look up existing customer by email (must already be registered)
    cust_res = await db.execute(select(Customer).where(Customer.email == data.customer_email))
    customer = cust_res.scalar_one_or_none()
    if not customer:
        raise NotFoundError(
            "Customer",
            data.customer_email,
            detail=f"No customer found with email '{data.customer_email}'. "
                   "The customer must register on the Payment Service before a checkout session can be created."
        )

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

    return CheckoutSessionResponse(
        session_id=str(session.id),
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
    "/{session_id}/authorize",
    response_model=CheckoutAuthorizeResponse,
    summary="Authorize a checkout session via EGS Bearer token",
)
async def authorize_checkout_session(
    session_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Authorize a checkout session using the user's EGS Auth Bearer token.
    
    The frontend must send an Authorization: Bearer <token> header obtained
    from the EGS Auth Service after the user logs in.
    """
    from sqlalchemy.orm import selectinload
    from app.services.auth_client import verify_token_with_auth_service

    # 1. Extract Bearer token from Authorization header
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header. Use: Bearer <token>")
    
    token = auth_header.split(" ", 1)[1]

    # 2. Verify token with EGS Auth Service
    try:
        verified = await verify_token_with_auth_service(token)
    except Exception:
        raise HTTPException(status_code=503, detail="Authentication service unavailable")
    
    if not verified:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # 3. Fetch checkout session + customer
    result = await db.execute(
        select(CheckoutSession)
        .options(selectinload(CheckoutSession.customer))
        .where(CheckoutSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise NotFoundError("CheckoutSession", str(session_id))
        
    if session.status != "open":
        raise HTTPException(
            status_code=400, detail=f"Checkout session is already {session.status}"
        )

    # 4. Ensure the verified user matches the session's customer
    customer = session.customer
    if customer.email != verified.email:
        raise HTTPException(
            status_code=403,
            detail="Authenticated user does not match the checkout session customer"
        )
        
    # 5. Create the internal payment as SUCCESS instantly
    payment = Payment(
        customer_id=customer.id,
        amount=session.amount_total,
        currency=session.currency,
        status="succeeded",
        description=f"Digital Wallet Transfer for Session: {session.id}",
        metadata_={"checkout_session_id": str(session.id), **(session.metadata_ or {})},
    )
    db.add(payment)
    await db.flush()
    await db.refresh(payment)
    
    # 6. Mark session completed
    session.payment_id = payment.id
    session.status = "complete"
    db.add(session)
    await db.commit()
    
    return CheckoutAuthorizeResponse(
        status="succeeded",
        payment_id=payment.id,
        success_url=session.success_url
    )


@router.get(
    "/{session_id}",
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

    return CheckoutSessionResponse(
        session_id=str(session.id),
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
