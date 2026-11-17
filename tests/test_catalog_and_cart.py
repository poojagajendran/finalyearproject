import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from backend.app.core.database import Base, get_db
from backend.app.main import app
from backend.app.services.catalog_seed import seed_initial_catalog

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False}
)

TestAsyncSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

async def override_get_db():
    async with TestAsyncSessionLocal() as session:
        yield session

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(autouse=True)
async def setup_test_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with TestAsyncSessionLocal() as session:
        await seed_initial_catalog(session)

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.mark.asyncio
async def test_catalog_and_cart_workflow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register User
        reg_res = await client.post("/api/v1/auth/register", json={
            "handle": "bob",
            "email": "bob@example.com",
            "full_name": "Bob Verma",
            "password": "Password123!"
        })
        assert reg_res.status_code == 201
        token = reg_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Verify categories
        cat_res = await client.get("/api/v1/products/categories")
        assert cat_res.status_code == 200
        categories = cat_res.json()
        assert len(categories) >= 3
        cat_slugs = [c["slug"] for c in categories]
        assert "audio" in cat_slugs

        # 3. Verify product search
        search_res = await client.get("/api/v1/products?search=earbuds")
        assert search_res.status_code == 200
        products = search_res.json()
        assert len(products) > 0
        product = products[0]
        assert "OnePlus" in product["title"]
        assert product["price_paise"] == 199900

        # 4. Filter by category
        audio_res = await client.get("/api/v1/products?category=audio")
        assert audio_res.status_code == 200
        assert all(p["category_slug"] == "audio" for p in audio_res.json())

        # 5. Add product to cart
        add_res = await client.post("/api/v1/cart/items", json={
            "product_id": product["id"],
            "quantity": 2
        }, headers=headers)
        assert add_res.status_code == 201
        cart = add_res.json()
        assert cart["total_items_count"] == 2
        # Price: 2 * 199900 = 399800 paise (₹3,998.00)
        assert cart["subtotal_paise"] == 399800
        # Tax: 18% of 399800 = 71964 paise (₹719.64)
        assert cart["tax_paise"] == (399800 * 18) // 100
        # Free delivery over ₹500
        assert cart["delivery_fee_paise"] == 0
        assert cart["total_paise"] == cart["subtotal_paise"] + cart["tax_paise"]

        # 6. Update cart item quantity
        item_id = cart["items"][0]["id"]
        update_res = await client.put(f"/api/v1/cart/items/{item_id}", json={
            "quantity": 3
        }, headers=headers)
        assert update_res.status_code == 200
        updated_cart = update_res.json()
        assert updated_cart["total_items_count"] == 3
        assert updated_cart["subtotal_paise"] == 3 * 199900

        # 7. Inventory stock limit check
        limit_res = await client.put(f"/api/v1/cart/items/{item_id}", json={
            "quantity": 1000  # More than stock
        }, headers=headers)
        # Should be rejected with 422 (pydantic le=10) or 400 (stock limit)
        assert limit_res.status_code in [400, 422]

        # 8. Delete cart item
        del_res = await client.delete(f"/api/v1/cart/items/{item_id}", headers=headers)
        assert del_res.status_code == 200
        assert del_res.json()["total_items_count"] == 0
        assert del_res.json()["total_paise"] == 0
