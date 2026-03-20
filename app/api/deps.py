"""
FastAPI dependency that verifies the user's Bearer token against the
external EGS Auth Service and returns a local Customer record.
"""

import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.customer import Customer
from app.services.auth_client import verify_token_with_auth_service

logger = logging.getLogger(__name__)
security = HTTPBearer()


async def get_current_customer(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> Customer:
    """Verify the Bearer token via the EGS Auth Service and return the
    matching local Customer record."""

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        verified = await verify_token_with_auth_service(credentials.credentials)
    except Exception:
        logger.exception("Failed to reach EGS Auth Service")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )

    if verified is None:
        raise credentials_exception

    # Look up local Customer by the verified email
    result = await db.execute(
        select(Customer).where(Customer.email == verified.email)
    )
    customer = result.scalar_one_or_none()

    if customer is None:
        # First wallet access for a valid Auth user: create local customer record
        # so dashboard/transactions endpoints can work immediately after login.
        customer = Customer(email=verified.email, is_active=True)
        db.add(customer)
        await db.flush()
        await db.refresh(customer)
        logger.info("Auto-provisioned wallet customer for %s", verified.email)

    return customer
