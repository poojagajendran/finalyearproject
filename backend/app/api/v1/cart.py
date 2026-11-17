from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.database import get_db
from backend.app.models.user import User
from backend.app.schemas.cart import CartResponse, CartItemCreate, CartItemUpdate
from backend.app.api.deps import get_current_user
from backend.app.services.cart_service import (
    get_user_cart,
    add_item_to_cart,
    update_cart_item,
    remove_cart_item,
    clear_user_cart
)

router = APIRouter(prefix="/cart", tags=["Shopping Cart"])

@router.get("", response_model=CartResponse)
async def view_cart(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve the current user's shopping cart with server-side pricing"""
    return await get_user_cart(db, current_user.id)

@router.post("/items", response_model=CartResponse, status_code=status.HTTP_201_CREATED)
async def add_to_cart(
    item_in: CartItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Add a product to cart or increase quantity"""
    return await add_item_to_cart(db, current_user.id, item_in.product_id, item_in.quantity)

@router.put("/items/{item_id}", response_model=CartResponse)
async def update_item_quantity(
    item_id: str,
    item_in: CartItemUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update item quantity in cart"""
    return await update_cart_item(db, current_user.id, item_id, item_in.quantity)

@router.delete("/items/{item_id}", response_model=CartResponse)
async def delete_item(
    item_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Remove a single item from the cart"""
    return await remove_cart_item(db, current_user.id, item_id)

@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def empty_cart(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Empty the entire shopping cart"""
    await clear_user_cart(db, current_user.id)
    return None
