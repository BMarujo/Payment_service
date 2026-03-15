from datetime import datetime, timedelta, timezone
import jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status
from typing import Optional
from app.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    settings = get_settings()
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        # Default session is 7 days for a digital wallet
        expire = datetime.now(timezone.utc) + timedelta(days=7)
        
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.stripe_webhook_secret, algorithm="HS256")
    return encoded_jwt
