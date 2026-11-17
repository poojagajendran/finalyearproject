from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    handle: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=100)
    vpa: Optional[str] = None
    phone: Optional[str] = None

class UserCreate(BaseModel):
    handle: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=6)
    vpa: Optional[str] = None
    phone: Optional[str] = None

class UserLogin(BaseModel):
    email_or_handle: str
    password: str

class UserResponse(BaseModel):
    id: str
    handle: str
    email: str
    full_name: str
    vpa: str
    phone: Optional[str] = None
    is_active: bool
    is_admin: bool
    created_at: datetime

    model_config = {"from_attributes": True}

class UserPublicProfile(BaseModel):
    id: str
    handle: str
    full_name: str
    vpa: str

    model_config = {"from_attributes": True}

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
