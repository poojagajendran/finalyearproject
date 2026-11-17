from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class CategoryResponse(BaseModel):
    slug: str
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None

    model_config = {"from_attributes": True}

class ProductBase(BaseModel):
    title: str
    slug: str
    description: str
    category_slug: str
    price_paise: int
    original_price_paise: int
    rating: float
    reviews_count: int
    image_url: str
    stock_quantity: int
    brand: str

class ProductResponse(ProductBase):
    id: str
    created_at: datetime

    model_config = {"from_attributes": True}

class ProductFilterParams(BaseModel):
    category: Optional[str] = None
    search: Optional[str] = None
    min_price_paise: Optional[int] = None
    max_price_paise: Optional[int] = None
    sort_by: Optional[str] = "rating"  # price_asc, price_desc, rating, popular
