import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import cast, String

from app.database import get_db
from app.models.customer import Customer
from app.config import get_settings

security = HTTPBearer()

async def get_current_customer(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> Customer:
    settings = get_settings()
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.stripe_webhook_secret,
            algorithms=["HS256"]
        )
        customer_id: str = payload.get("sub")
        if customer_id is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
        
    result = await db.execute(select(Customer).where(cast(Customer.id, type_=str) == customer_id))
    customer = result.scalar_one_or_none()
    
    if customer is None:
        raise credentials_exception
        
    return customer
