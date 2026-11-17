from pydantic import BaseModel, Field
from typing import List
from datetime import datetime
from backend.app.schemas.product import ProductResponse

class CartItemCreate(BaseModel):
    product_id: str
    quantity: int = Field(default=1, ge=1, le=10)

class CartItemUpdate(BaseModel):
    quantity: int = Field(..., ge=1, le=10)

class CartItemResponse(BaseModel):
    id: str
    product_id: str
    product: ProductResponse
    quantity: int
    line_total_paise: int
    created_at: datetime

    model_config = {"from_attributes": True}

class CartResponse(BaseModel):
    items: List[CartItemResponse]
    total_items_count: int
    subtotal_paise: int
    tax_paise: int
    delivery_fee_paise: int
    total_paise: int
