from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.security import hash_password, verify_password, create_access_token
from backend.app.models.user import User
from backend.app.schemas.user import UserCreate, UserLogin, UserResponse, UserPublicProfile, TokenResponse
from backend.app.api.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])

def set_auth_cookie(response: Response, token: str) -> None:
    """Sets secure HTTP-only cookie for session management"""
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        expires=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=(settings.APP_ENV == "production")
    )

def clear_auth_cookie(response: Response) -> None:
    """Clears the session cookie"""
    response.delete_cookie(
        key=settings.COOKIE_NAME,
        httponly=True,
        samesite="lax"
    )

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_in: UserCreate,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """Registers a new user and issues an authenticated session"""
    # Check if handle exists
    existing_handle = await db.execute(select(User).where(User.handle == user_in.handle.lower()))
    if existing_handle.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Handle '@{user_in.handle}' is already registered."
        )

    # Check if email exists
    existing_email = await db.execute(select(User).where(User.email == user_in.email.lower()))
    if existing_email.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists."
        )

    # Derive default VPA if not provided
    default_vpa = user_in.vpa or f"{user_in.handle.lower()}@simbank"
    existing_vpa = await db.execute(select(User).where(User.vpa == default_vpa))
    if existing_vpa.scalar_one_or_none():
        default_vpa = f"{user_in.handle.lower()}_{int(user_in.handle.__hash__() % 1000)}@simbank"

    new_user = User(
        handle=user_in.handle.lower(),
        email=user_in.email.lower(),
        full_name=user_in.full_name,
        hashed_password=hash_password(user_in.password),
        vpa=default_vpa,
        phone=user_in.phone
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    access_token = create_access_token(subject=new_user.id)
    set_auth_cookie(response, access_token)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(new_user)
    )

@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: UserLogin,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """Authenticates user via email/handle + password with Argon2id"""
    identifier = credentials.email_or_handle.strip().lower()
    if identifier.startswith("@"):
        identifier = identifier[1:]

    result = await db.execute(
        select(User).where(
            or_(
                User.email == identifier,
                User.handle == identifier
            )
        )
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials. Please verify your handle/email and password."
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated."
        )

    access_token = create_access_token(subject=user.id)
    set_auth_cookie(response, access_token)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user)
    )

@router.post("/logout")
async def logout(response: Response):
    """Terminates authenticated session by clearing HTTP-only cookie"""
    clear_auth_cookie(response)
    return {"message": "Logged out successfully"}

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Returns the authenticated user profile"""
    return UserResponse.model_validate(current_user)

@router.get("/users/by-handle/{handle}", response_model=UserPublicProfile)
async def get_user_by_handle(
    handle: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    """Lookup participant public profile by handle (without @)"""
    clean_handle = handle.lower().lstrip("@")
    result = await db.execute(select(User).where(User.handle == clean_handle))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '@{clean_handle}' not found."
        )
    return UserPublicProfile.model_validate(user)

@router.get("/users/search", response_model=List[UserPublicProfile])
async def search_users(
    q: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user)
):
    """Search registered users for group purchase invitations"""
    query = f"%{q.lower().lstrip('@')}%"
    result = await db.execute(
        select(User).where(
            or_(
                User.handle.ilike(query),
                User.full_name.ilike(query)
            )
        ).limit(10)
    )
    users = result.scalars().all()
    return [UserPublicProfile.model_validate(u) for u in users]
