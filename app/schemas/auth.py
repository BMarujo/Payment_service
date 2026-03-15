from pydantic import BaseModel, EmailStr, Field

class CustomerRegister(BaseModel):
    email: EmailStr = Field(..., description="Customer email address")
    name: str = Field(..., description="Customer full name")
    password: str = Field(..., min_length=8, description="Secure account password")

class CustomerLogin(BaseModel):
    email: EmailStr = Field(..., description="Customer email address")
    password: str = Field(..., description="Account password")

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
