import re
from typing import List, Dict, Any, Optional
import anthropic
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.config import settings
from backend.app.models.user import User
from backend.app.schemas.ai import ChatRequest, ChatResponse, ToolCallRecord
from backend.app.services.ai_tools import ANTHROPIC_TOOLS, execute_tool

SYSTEM_PROMPT = """You are ShopCart AI, an expert collaborative e-commerce shopping assistant.
You assist users with:
1. Finding and comparing products in the catalog.
2. Managing the shopping cart.
3. Setting up multi-user group purchases and payment splits.
4. Explaining group payment statuses (LOCKED, PENDING, DEBITED, DECLINED).
5. Offering dynamic redistribution resolutions when participants decline.

CRITICAL PAYMENT SECURITY RULES:
- You must NEVER attempt or claim to approve, debit, refund, or release payments directly.
- Financial authorizations require human PIN entry at SimBank.
- All monetary amounts in conversation are expressed in Indian Rupees (₹).
- When a group purchase is prepared, inform users that each participant will need to enter their UPI PIN to lock funds.
"""

class ShoppingAgent:
    def __init__(self):
        self.api_key = settings.ANTHROPIC_API_KEY
        self.model = settings.ANTHROPIC_MODEL
        self.is_mock = settings.MOCK_ANTHROPIC or not self.api_key or self.api_key.startswith("mock-")
        if not self.is_mock:
            self.client = anthropic.AsyncAnthropic(api_key=self.api_key)
        else:
            self.client = None

    async def chat(
        self,
        req: ChatRequest,
        user: User,
        db: AsyncSession
    ) -> ChatResponse:
        """Process user message and execute tool calls"""
        if not self.is_mock and self.client:
            return await self._run_anthropic_agent(req, user, db)
        else:
            return await self._run_deterministic_agent(req, user, db)

    async def _run_anthropic_agent(
        self,
        req: ChatRequest,
        user: User,
        db: AsyncSession
    ) -> ChatResponse:
        """Calls official Anthropic Claude API with function/tool calling"""
        messages = [{"role": m.role, "content": m.content} for m in req.conversation_history]
        messages.append({"role": "user", "content": req.message})

        tool_records: List[ToolCallRecord] = []

        # Initial Claude invocation
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=messages,
            tools=ANTHROPIC_TOOLS
        )

        # Check if Claude called tools
        if response.stop_reason == "tool_use":
            tool_results_content = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_args = block.input
                    tool_id = block.id

                    # Execute tool in backend with authenticated user context
                    output = await execute_tool(
                        tool_name=tool_name,
                        args=tool_args,
                        user=user,
                        db=db,
                        active_group_id=req.active_group_id
                    )

                    tool_records.append(
                        ToolCallRecord(tool_name=tool_name, args=tool_args, output=output)
                    )

                    tool_results_content.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": str(output)
                    })

            # Feed tool results back to Claude
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results_content})

            second_res = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=messages
            )

            reply_text = "".join([b.text for b in second_res.content if hasattr(b, "text")])
            return ChatResponse(
                reply=reply_text,
                tool_calls=tool_records,
                suggested_actions=["View Cart", "Check Group Status", "Explore Audio"]
            )

        reply_text = "".join([b.text for b in response.content if hasattr(b, "text")])
        return ChatResponse(
            reply=reply_text,
            tool_calls=[],
            suggested_actions=["Find wireless earbuds under ₹2,000", "View my cart"]
        )

    async def _run_deterministic_agent(
        self,
        req: ChatRequest,
        user: User,
        db: AsyncSession
    ) -> ChatResponse:
        """
        Intelligent deterministic agent for testing and local execution without API keys.
        Understands natural language commands and executes real backend tools.
        """
        msg = req.message.strip().lower()
        tool_records: List[ToolCallRecord] = []
        ui_card = None

        # 1. Product Search (e.g. "find wireless earbuds under ₹2000", "search headphones")
        if any(w in msg for w in ["find", "search", "show me", "recommend", "looking for"]):
            max_price = None
            price_match = re.search(r"(?:under|below|less than|up to)?\s*(?:₹|rs\.?|inr)?\s*([0-9]+(?:,[0-9]+)?)", msg)
            if price_match:
                max_price = float(price_match.group(1).replace(",", ""))

            query = ""
            if "earbud" in msg:
                query = "earbuds"
            elif "headphone" in msg:
                query = "headphones"
            elif "watch" in msg:
                query = "watch"
            elif "keyboard" in msg:
                query = "keyboard"
            elif "mouse" in msg:
                query = "mouse"
            elif "charger" in msg:
                query = "charger"
            elif "power bank" in msg:
                query = "power bank"
            elif "tablet" in msg or "kindle" in msg:
                query = "kindle"

            args = {"query": query, "max_price_rupees": max_price}
            res = await execute_tool("search_products", args, user, db)
            tool_records.append(ToolCallRecord(tool_name="search_products", args=args, output=res))

            prods = res.get("products", [])
            if prods:
                p_list = "\n".join([f"• **{p['title']}** — ₹{p['price_rupees']:,.2f} (⭐ {p['rating']}/5)" for p in prods[:3]])
                reply = (
                    f"I found {len(prods)} product(s) matching your request:\n\n{p_list}\n\n"
                    "Would you like me to add any of these to your shopping cart?"
                )
                ui_card = {"type": "products_carousel", "products": prods[:4]}
            else:
                reply = "I couldn't find any products matching those exact criteria. Would you like to check all audio products or smartwatches?"

            return ChatResponse(
                reply=reply,
                tool_calls=tool_records,
                suggested_actions=["Add OnePlus Nord Buds 2 to cart", "View my cart"],
                ui_card=ui_card
            )

        # 2. Add to Cart (e.g. "add this product to my cart", "add oneplus nord buds to cart")
        elif "add" in msg and "cart" in msg:
            # Search product first
            target_slug = "oneplus-nord-buds-2"
            if "boat" in msg:
                target_slug = "boat-rockerz-450"
            elif "sony" in msg:
                target_slug = "sony-wh-1000xm5"
            elif "apple" in msg or "airpods" in msg:
                target_slug = "apple-airpods-pro-2"
            elif "keyboard" in msg or "keychron" in msg:
                target_slug = "keychron-k2-wireless"

            prod_res = await execute_tool("get_product", {"product_id_or_slug": target_slug}, user, db)
            if "error" not in prod_res:
                add_res = await execute_tool("add_to_cart", {"product_id": prod_res["id"], "quantity": 1}, user, db)
                tool_records.append(ToolCallRecord(tool_name="add_to_cart", args={"product_id": prod_res["id"]}, output=add_res))
                reply = f"✅ Added **{prod_res['title']}** to your cart! Your current cart total is **₹{add_res['cart_total_rupees']:,.2f}**."
                ui_card = {"type": "cart_notification", "product": prod_res, "cart_total": add_res["cart_total_rupees"]}
            else:
                reply = "Which product would you like to add? Please specify the name or title."

            return ChatResponse(
                reply=reply,
                tool_calls=tool_records,
                suggested_actions=["View my cart", "Split payment with Ravi, Meena"],
                ui_card=ui_card
            )

        # 3. View Cart
        elif "cart" in msg and any(w in msg for w in ["view", "show", "check", "what", "my cart", "open"]):
            cart_res = await execute_tool("view_cart", {}, user, db)
            tool_records.append(ToolCallRecord(tool_name="view_cart", args={}, output=cart_res))
            if cart_res["total_items_count"] > 0:
                items_str = "\n".join([f"• {it['title']} (Qty: {it['quantity']}) — ₹{it['line_total_rupees']:,.2f}" for it in cart_res["items"]])
                reply = (
                    f"🛒 **Your Shopping Cart ({cart_res['total_items_count']} items)**:\n\n{items_str}\n\n"
                    f"**Subtotal:** ₹{cart_res['subtotal_rupees']:,.2f}\n"
                    f"**GST (18%):** ₹{cart_res['tax_rupees']:,.2f}\n"
                    f"**Total:** ₹{cart_res['total_rupees']:,.2f}\n\n"
                    "Would you like to initiate a group purchase with friends to split this cost?"
                )
                ui_card = {"type": "cart_summary", "cart": cart_res}
            else:
                reply = "Your shopping cart is currently empty. Can I help you find something?"

            return ChatResponse(reply=reply, tool_calls=tool_records, suggested_actions=["Find wireless earbuds", "Explore bestsellers"], ui_card=ui_card)

        # 4. Group Checkout / Split (e.g. "split the payment with ravi, meena and kiran")
        elif "split" in msg or "group" in msg or "checkout" in msg:
            handles = []
            for candidate in ["ravi", "meena", "kiran", "bob"]:
                if candidate in msg and candidate != user.handle:
                    handles.append(candidate)
            if not handles:
                handles = ["ravi", "meena"]  # default co-purchasers

            args = {"participant_handles": handles, "split_type": "EQUAL"}
            res = await execute_tool("prepare_checkout", args, user, db)
            tool_records.append(ToolCallRecord(tool_name="prepare_checkout", args=args, output=res))

            if "error" in res:
                reply = f"Could not prepare group purchase: {res['error']}"
            else:
                p_shares = ", ".join([f"@{p['handle']} (₹{p['share_rupees']:,.2f})" for p in res["participants"]])
                reply = (
                    f"👥 Prepared group purchase (**Total: ₹{res['total_rupees']:,.2f}**) split equally between {len(res['participants'])} members:\n"
                    f"{p_shares}.\n\n"
                    "The group order is in **COLLECTING** status. To authorize payment, each participant must enter their SimBank PIN. "
                    "Funds remain securely held in each participant's bank account until all participants authorize."
                )
                ui_card = {"type": "group_proposal", "group": res}

            return ChatResponse(
                reply=reply,
                tool_calls=tool_records,
                suggested_actions=["Show me who has paid", "View group dashboard"],
                ui_card=ui_card
            )

        # 5. Check Group Status (e.g. "show me who has paid", "what is the group status?")
        elif any(w in msg for w in ["who has paid", "status", "who paid", "group status"]):
            gid = req.active_group_id
            res = await execute_tool("get_group_status", {"group_id": gid}, user, db, active_group_id=gid)
            tool_records.append(ToolCallRecord(tool_name="get_group_status", args={"group_id": gid}, output=res))

            if "error" in res:
                reply = "Please open an active group order from the Group Dashboard to view participant authorization progress."
            else:
                status_list = "\n".join([f"• **@{p['handle']}** ({p['name']}): `{p['approval_status']}` (₹{p['share_rupees']:,.2f})" for p in res["participants"]])
                reply = (
                    f"📊 **Group Status: {res['status']}** (Total: ₹{res['total_rupees']:,.2f})\n\n"
                    f"{status_list}\n\n"
                    "Once all participants lock their shares, the order will automatically commit."
                )
                ui_card = {"type": "group_status", "status": res}

            return ChatResponse(reply=reply, tool_calls=tool_records, suggested_actions=["Check again", "Offer resolution"], ui_card=ui_card)

        # 6. Decline Resolution / Recovery (e.g. "ravi declined. what can i do?")
        elif any(w in msg for w in ["declined", "opted out", "resolution", "what can i do", "failed"]):
            gid = req.active_group_id
            res = await execute_tool("offer_resolution", {"group_id": gid}, user, db, active_group_id=gid)
            tool_records.append(ToolCallRecord(tool_name="offer_resolution", args={"group_id": gid}, output=res))

            if "error" in res:
                reply = "To resolve a declined participant, navigate to the Group Payment Recovery screen."
            else:
                shares = ", ".join([f"@{h}: ₹{amt:,.2f}" for h, amt in res["proposed_shares_rupees"].items()])
                reply = (
                    f"⚠️ **Dynamic Redistribution Plan**:\n\n{res['explanation']}\n\n"
                    f"**Proposed Revised Shares:** {shares}\n\n"
                    "👉 Click **Apply Redistribution** on the dashboard. Note: As per payment security rules, "
                    "remaining members must explicitly re-authorize their revised shares before funds can be debited."
                )
                ui_card = {"type": "recovery_proposal", "resolution": res}

            return ChatResponse(
                reply=reply,
                tool_calls=tool_records,
                suggested_actions=["Apply Redistribution", "Abort Group Order"],
                ui_card=ui_card
            )

        # Default Helpful Response
        return ChatResponse(
            reply=(
                "Hello! I am your ShopCart AI Assistant. I can help you find products, manage your cart, "
                "or set up collaborative split payments. Try asking:\n\n"
                "• *'Find wireless earbuds under ₹2,000'*\n"
                "• *'Add boAt Rockerz 450 to my cart'*\n"
                "• *'Split the payment with Ravi and Meena'*\n"
                "• *'Show me who has paid'*"
            ),
            tool_calls=[],
            suggested_actions=["Find wireless earbuds under ₹2,000", "View my cart"]
        )

ai_agent = ShoppingAgent()
