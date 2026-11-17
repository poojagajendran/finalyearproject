import re
from typing import Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_
from fastapi import HTTPException
from backend.app.models.user import User
from backend.app.models.product import Product
from backend.app.services.cart_service import (
    get_user_cart, add_item_to_cart, remove_cart_item
)
from backend.app.services.group_service import (
    create_group_from_cart, get_group_purchase, propose_dynamic_resplit
)
from backend.app.schemas.group import CreateGroupRequest

# Anthropic Tool Calling Specifications
ANTHROPIC_TOOLS = [
    {
        "name": "search_products",
        "description": "Search products in the catalog by keyword, category, or maximum price in rupees.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query keywords (e.g. 'earbuds', 'watch', 'boat')"},
                "category": {"type": "string", "description": "Category slug (e.g. 'audio', 'wearables', 'accessories', 'tablets')"},
                "max_price_rupees": {"type": "number", "description": "Maximum price in Indian Rupees (e.g. 2000 for ₹2,000)"}
            }
        }
    },
    {
        "name": "get_product",
        "description": "Fetch detailed specifications, price, and stock for a specific product by slug or ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id_or_slug": {"type": "string", "description": "Unique product UUID or slug string"}
            },
            "required": ["product_id_or_slug"]
        }
    },
    {
        "name": "view_cart",
        "description": "View all items currently in the authenticated user's shopping cart along with subtotal, tax, delivery fee, and total.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "add_to_cart",
        "description": "Add an item to the shopping cart or increase its quantity.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "Product UUID"},
                "quantity": {"type": "integer", "description": "Quantity to add (default: 1)", "default": 1}
            },
            "required": ["product_id"]
        }
    },
    {
        "name": "remove_from_cart",
        "description": "Remove an item from the shopping cart by item ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item_id": {"type": "string", "description": "Cart item UUID"}
            },
            "required": ["item_id"]
        }
    },
    {
        "name": "prepare_checkout",
        "description": "Prepare a collaborative group checkout proposal by splitting cart total among invited participant handles. Note: This creates a proposal in COLLECTING state; it does NOT authorize or debit any payment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "participant_handles": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Handles of friends to split with (without @, e.g. ['ravi', 'meena'])"
                },
                "split_type": {
                    "type": "string",
                    "enum": ["EQUAL", "CUSTOM"],
                    "description": "Split strategy, default EQUAL",
                    "default": "EQUAL"
                }
            },
            "required": ["participant_handles"]
        }
    },
    {
        "name": "get_group_status",
        "description": "Retrieve current real-time status, participant approvals, holds, and debits for an active group purchase.",
        "input_schema": {
            "type": "object",
            "properties": {
                "group_id": {"type": "string", "description": "UUID of the group purchase"}
            },
            "required": ["group_id"]
        }
    },
    {
        "name": "offer_resolution",
        "description": "Generate a dynamic redistribution proposal when a participant has declined or opted out, calculating revised shares for remaining members.",
        "input_schema": {
            "type": "object",
            "properties": {
                "group_id": {"type": "string", "description": "UUID of the group purchase in RESPLIT_PENDING state"}
            },
            "required": ["group_id"]
        }
    }
]

async def execute_tool(
    tool_name: str,
    args: Dict[str, Any],
    user: User,
    db: AsyncSession,
    active_group_id: str | None = None
) -> Dict[str, Any]:
    """
    Executes tool with strict session security guarantees:
    - User identity bound to authenticated session (never from LLM parameters).
    - Read and propose ONLY: strictly blocked from debiting, releasing, or approving funds.
    """
    if tool_name == "search_products":
        query = select(Product)
        filters = []
        if args.get("query"):
            term = f"%{args['query'].strip()}%"
            filters.append(or_(Product.title.ilike(term), Product.description.ilike(term), Product.brand.ilike(term)))
        if args.get("category"):
            filters.append(Product.category_slug == args["category"].lower())
        if args.get("max_price_rupees"):
            max_paise = int(args["max_price_rupees"] * 100)
            filters.append(Product.price_paise <= max_paise)
        if filters:
            query = query.where(and_(*filters))
        query = query.limit(6)
        res = await db.execute(query)
        prods = res.scalars().all()
        return {
            "count": len(prods),
            "products": [
                {
                    "id": p.id,
                    "title": p.title,
                    "slug": p.slug,
                    "price_rupees": p.price_paise / 100,
                    "rating": p.rating,
                    "image_url": p.image_url,
                    "brand": p.brand
                }
                for p in prods
            ]
        }

    elif tool_name == "get_product":
        target = args["product_id_or_slug"]
        query = select(Product).where(or_(Product.id == target, Product.slug == target.lower()))
        res = await db.execute(query)
        p = res.scalar_one_or_none()
        if not p:
            return {"error": f"Product '{target}' not found"}
        return {
            "id": p.id,
            "title": p.title,
            "slug": p.slug,
            "description": p.description,
            "price_rupees": p.price_paise / 100,
            "original_price_rupees": p.original_price_paise / 100,
            "rating": p.rating,
            "stock_quantity": p.stock_quantity,
            "brand": p.brand
        }

    elif tool_name == "view_cart":
        cart = await get_user_cart(db, user.id)
        return {
            "total_items_count": cart.total_items_count,
            "subtotal_rupees": cart.subtotal_paise / 100,
            "tax_rupees": cart.tax_paise / 100,
            "delivery_fee_rupees": cart.delivery_fee_paise / 100,
            "total_rupees": cart.total_paise / 100,
            "items": [
                {
                    "item_id": it.id,
                    "product_id": it.product_id,
                    "title": it.product.title,
                    "quantity": it.quantity,
                    "line_total_rupees": it.line_total_paise / 100
                }
                for it in cart.items
            ]
        }

    elif tool_name == "add_to_cart":
        qty = args.get("quantity", 1)
        cart = await add_item_to_cart(db, user.id, args["product_id"], qty)
        return {
            "message": f"Successfully added to cart. Total items: {cart.total_items_count}",
            "cart_total_rupees": cart.total_paise / 100
        }

    elif tool_name == "remove_from_cart":
        cart = await remove_cart_item(db, user.id, args["item_id"])
        return {
            "message": "Item removed from cart.",
            "cart_total_rupees": cart.total_paise / 100
        }

    elif tool_name == "prepare_checkout":
        handles = [h.strip().lstrip("@") for h in args["participant_handles"]]
        req = CreateGroupRequest(
            title=f"{user.full_name}'s Shared Order",
            strategy="LOCK",
            split_type=args.get("split_type", "EQUAL"),
            participant_handles=handles
        )
        group = await create_group_from_cart(db, user, req)
        return {
            "group_id": group.id,
            "status": group.status,
            "total_rupees": group.total_paise / 100,
            "participants": [
                {
                    "handle": p.user.handle,
                    "share_rupees": p.allocated_share_paise / 100,
                    "status": p.approval_status
                }
                for p in group.participants
            ],
            "note": "Group purchase initialized in COLLECTING state. Each participant must authorize their share using their PIN."
        }

    elif tool_name == "get_group_status":
        gid = args.get("group_id") or active_group_id
        if not gid:
            return {"error": "Missing group_id"}
        group = await get_group_purchase(db, gid)
        return {
            "group_id": group.id,
            "status": group.status,
            "total_rupees": group.total_paise / 100,
            "order_id": group.order_id,
            "participants": [
                {
                    "handle": p.user.handle,
                    "name": p.user.full_name,
                    "share_rupees": p.allocated_share_paise / 100,
                    "approval_status": p.approval_status,
                    "reapproval_needed": p.reapproval_needed,
                    "declined_reason": p.declined_reason
                }
                for p in group.participants
            ]
        }

    elif tool_name == "offer_resolution":
        gid = args.get("group_id") or active_group_id
        if not gid:
            return {"error": "Missing group_id"}
        prop = await propose_dynamic_resplit(db, gid)
        return {
            "group_id": prop.group_id,
            "status": prop.status,
            "declined": prop.declined_participants,
            "proposed_shares_rupees": {h: p/100 for h, p in prop.proposed_allocations.items()},
            "explanation": prop.explanation,
            "action": "Host can confirm this redistribution on the dashboard to prompt remaining members for reapproval."
        }

    else:
        return {"error": f"Unknown tool: {tool_name}"}
