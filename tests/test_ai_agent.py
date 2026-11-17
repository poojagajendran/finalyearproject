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
async def test_ai_shopping_agent_workflow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register Alice, Ravi, Meena
        res_alice = await client.post("/api/v1/auth/register", json={
            "handle": "alice", "email": "alice@ai.com", "full_name": "Alice Sharma", "password": "Password123!"
        })
        headers_alice = {"Authorization": f"Bearer {res_alice.json()['access_token']}"}

        await client.post("/api/v1/auth/register", json={
            "handle": "ravi", "email": "ravi@ai.com", "full_name": "Ravi Kumar", "password": "Password123!"
        })
        await client.post("/api/v1/auth/register", json={
            "handle": "meena", "email": "meena@ai.com", "full_name": "Meena Patel", "password": "Password123!"
        })

        # 2. Natural language product discovery
        chat_search = await client.post("/api/v1/ai/chat", json={
            "message": "Find wireless earbuds under ₹2,000"
        }, headers=headers_alice)
        assert chat_search.status_code == 200
        search_data = chat_search.json()
        assert len(search_data["tool_calls"]) > 0
        assert search_data["tool_calls"][0]["tool_name"] == "search_products"
        assert "OnePlus" in search_data["reply"] or "found" in search_data["reply"].lower()

        # 3. Natural language add to cart
        chat_add = await client.post("/api/v1/ai/chat", json={
            "message": "Add OnePlus Nord Buds to my cart"
        }, headers=headers_alice)
        assert chat_add.status_code == 200
        add_data = chat_add.json()
        assert any(tc["tool_name"] == "add_to_cart" for tc in add_data["tool_calls"])
        assert "Added" in add_data["reply"] or "cart" in add_data["reply"].lower()

        # 4. Natural language view cart
        chat_view = await client.post("/api/v1/ai/chat", json={
            "message": "View my shopping cart"
        }, headers=headers_alice)
        assert chat_view.status_code == 200
        assert any(tc["tool_name"] == "view_cart" for tc in chat_view.json()["tool_calls"])

        # 5. Natural language split checkout preparation
        chat_split = await client.post("/api/v1/ai/chat", json={
            "message": "Split the payment with Ravi and Meena"
        }, headers=headers_alice)
        assert chat_split.status_code == 200
        split_data = chat_split.json()
        assert any(tc["tool_name"] == "prepare_checkout" for tc in split_data["tool_calls"])
        assert "COLLECTING" in split_data["reply"] or "group" in split_data["reply"].lower()

        # 6. Verify security boundary: Agent cannot debit or lock funds directly
        # The tools available to Claude do NOT include debit_funds or release_funds
        tool_names = [tc["tool_name"] for tc in split_data["tool_calls"]]
        assert "debit_funds" not in tool_names
        assert "lock_funds" not in tool_names
