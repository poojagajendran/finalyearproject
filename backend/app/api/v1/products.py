from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, desc, asc
from backend.app.core.database import get_db
from backend.app.models.product import Category, Product
from backend.app.schemas.product import CategoryResponse, ProductResponse

router = APIRouter(prefix="/products", tags=["Products & Catalog"])

@router.get("/categories", response_model=List[CategoryResponse])
async def list_categories(db: AsyncSession = Depends(get_db)):
    """Retrieve all product categories"""
    result = await db.execute(select(Category).order_by(Category.name))
    return result.scalars().all()

@router.get("", response_model=List[ProductResponse])
async def list_products(
    category: Optional[str] = Query(None, description="Category slug"),
    search: Optional[str] = Query(None, description="Keyword search in title or description"),
    min_price_paise: Optional[int] = Query(None, description="Minimum price in integer paise"),
    max_price_paise: Optional[int] = Query(None, description="Maximum price in integer paise"),
    sort_by: Optional[str] = Query("rating", description="rating, price_asc, price_desc, newest"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    """Retrieve catalog products with server-side filtering, search, and sorting"""
    query = select(Product)
    filters = []

    if category:
        filters.append(Product.category_slug == category.lower())
    
    if search:
        search_term = f"%{search.strip().lower()}%"
        filters.append(
            or_(
                Product.title.ilike(search_term),
                Product.description.ilike(search_term),
                Product.brand.ilike(search_term)
            )
        )

    if min_price_paise is not None:
        filters.append(Product.price_paise >= min_price_paise)

    if max_price_paise is not None:
        filters.append(Product.price_paise <= max_price_paise)

    if filters:
        query = query.where(and_(*filters))

    # Sorting
    if sort_by == "price_asc":
        query = query.order_by(asc(Product.price_paise))
    elif sort_by == "price_desc":
        query = query.order_by(desc(Product.price_paise))
    elif sort_by == "newest":
        query = query.order_by(desc(Product.created_at))
    else:  # default: rating
        query = query.order_by(desc(Product.rating), desc(Product.reviews_count))

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()

@router.get("/{product_id_or_slug}", response_model=ProductResponse)
async def get_product(
    product_id_or_slug: str,
    db: AsyncSession = Depends(get_db)
):
    """Get single product by UUID id or unique slug"""
    query = select(Product).where(
        or_(
            Product.id == product_id_or_slug,
            Product.slug == product_id_or_slug.lower()
        )
    )
    result = await db.execute(query)
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    return product
