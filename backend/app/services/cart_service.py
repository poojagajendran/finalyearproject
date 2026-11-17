from typing import List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from backend.app.models.product import CartItem, Product
from backend.app.schemas.cart import CartResponse, CartItemResponse

def calculate_cart_totals(items: List[CartItem]) -> Tuple[int, int, int, int]:
    """
    Computes financial breakdown in integer paise:
    - subtotal_paise
    - tax_paise (18% GST)
    - delivery_fee_paise (Free over ₹500, else ₹40 = 4000 paise)
    - total_paise
    """
    subtotal_paise = 0
    total_items = 0

    for item in items:
        line_total = item.quantity * item.product.price_paise
        subtotal_paise += line_total
        total_items += item.quantity

    if subtotal_paise == 0:
        return 0, 0, 0, 0

    # 18% GST calculated accurately via integer math
    tax_paise = (subtotal_paise * 18) // 100
    
    # Free delivery above ₹500 (50,000 paise), else ₹40 (4,000 paise)
    delivery_fee_paise = 0 if subtotal_paise >= 50000 else 4000
    
    total_paise = subtotal_paise + tax_paise + delivery_fee_paise
    return subtotal_paise, tax_paise, delivery_fee_paise, total_paise

async def get_user_cart(db: AsyncSession, user_id: str) -> CartResponse:
    """Fetch user's cart items with joined product information and computed totals"""
    stmt = (
        select(CartItem)
        .where(CartItem.user_id == user_id)
        .options(selectinload(CartItem.product))
        .order_by(CartItem.created_at.desc())
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    subtotal, tax, delivery, total = calculate_cart_totals(items)

    item_responses = [
        CartItemResponse(
            id=item.id,
            product_id=item.product_id,
            product=item.product,
            quantity=item.quantity,
            line_total_paise=item.quantity * item.product.price_paise,
            created_at=item.created_at
        )
        for item in items
    ]

    return CartResponse(
        items=item_responses,
        total_items_count=sum(item.quantity for item in items),
        subtotal_paise=subtotal,
        tax_paise=tax,
        delivery_fee_paise=delivery,
        total_paise=total
    )

async def add_item_to_cart(db: AsyncSession, user_id: str, product_id: str, quantity: int) -> CartResponse:
    """Add product to cart or increment quantity, with stock verification"""
    prod_stmt = select(Product).where(Product.id == product_id)
    prod_res = await db.execute(prod_stmt)
    product = prod_res.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    # Check existing item
    cart_stmt = select(CartItem).where(CartItem.user_id == user_id, CartItem.product_id == product_id)
    cart_res = await db.execute(cart_stmt)
    cart_item = cart_res.scalar_one_or_none()

    target_qty = quantity
    if cart_item:
        target_qty = cart_item.quantity + quantity

    if target_qty > product.stock_quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Requested quantity ({target_qty}) exceeds available stock ({product.stock_quantity})"
        )

    if cart_item:
        cart_item.quantity = target_qty
    else:
        cart_item = CartItem(user_id=user_id, product_id=product_id, quantity=quantity)
        db.add(cart_item)

    await db.commit()
    return await get_user_cart(db, user_id)

async def update_cart_item(db: AsyncSession, user_id: str, item_id: str, quantity: int) -> CartResponse:
    """Update item quantity in cart"""
    cart_stmt = (
        select(CartItem)
        .where(CartItem.id == item_id, CartItem.user_id == user_id)
        .options(selectinload(CartItem.product))
    )
    cart_res = await db.execute(cart_stmt)
    cart_item = cart_res.scalar_one_or_none()

    if not cart_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")

    if quantity > cart_item.product.stock_quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Quantity {quantity} exceeds available stock ({cart_item.product.stock_quantity})"
        )

    cart_item.quantity = quantity
    await db.commit()
    return await get_user_cart(db, user_id)

async def remove_cart_item(db: AsyncSession, user_id: str, item_id: str) -> CartResponse:
    """Remove item from cart"""
    stmt = delete(CartItem).where(CartItem.id == item_id, CartItem.user_id == user_id)
    await db.execute(stmt)
    await db.commit()
    return await get_user_cart(db, user_id)

async def clear_user_cart(db: AsyncSession, user_id: str) -> None:
    """Clear all items in cart"""
    stmt = delete(CartItem).where(CartItem.user_id == user_id)
    await db.execute(stmt)
    await db.commit()
