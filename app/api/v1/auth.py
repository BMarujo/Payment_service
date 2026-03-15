from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.customer import Customer
from app.schemas.auth import CustomerRegister, CustomerLogin, TokenResponse
from app.services.auth_service import get_password_hash, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register_customer(
    data: CustomerRegister,
    db: AsyncSession = Depends(get_db)
):
    # Check if user exists
    result = await db.execute(select(Customer).where(Customer.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new customer with password
    hashed = get_password_hash(data.password)
    customer = Customer(
        email=data.email,
        name=data.name,
        hashed_password=hashed
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    
    # Generate token
    token = create_access_token(data={"sub": str(customer.id), "email": customer.email})
    return TokenResponse(access_token=token, token_type="bearer")


@router.post("/login", response_model=TokenResponse)
async def login_customer(
    data: CustomerLogin,
    db: AsyncSession = Depends(get_db)
):
    # Authenticate
    result = await db.execute(select(Customer).where(Customer.email == data.email))
    customer = result.scalar_one_or_none()
    
    if not customer or not customer.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if not verify_password(data.password, customer.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    # Generate token
    token = create_access_token(data={"sub": str(customer.id), "email": customer.email})
    return TokenResponse(access_token=token, token_type="bearer")
