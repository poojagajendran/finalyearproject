import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from backend.app.core.database import Base, get_db
from backend.app.main import app

# Test database using in-memory SQLite
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

@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.mark.asyncio
async def test_register_and_login_flow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register Alice
        reg_payload = {
            "handle": "alice",
            "email": "alice@example.com",
            "full_name": "Alice Sharma",
            "password": "SecurePassword123!"
        }
        res = await client.post("/api/v1/auth/register", json=reg_payload)
        assert res.status_code == 201, res.text
        data = res.json()
        assert data["user"]["handle"] == "alice"
        assert data["user"]["vpa"] == "alice@simbank"
        assert "access_token" in data
        assert "shopcart_token" in res.cookies

        # 2. Prevent duplicate handle
        res_dup = await client.post("/api/v1/auth/register", json=reg_payload)
        assert res_dup.status_code == 400
        assert "already registered" in res_dup.json()["detail"]

        # 3. Log in with handle
        login_res = await client.post("/api/v1/auth/login", json={
            "email_or_handle": "alice",
            "password": "SecurePassword123!"
        })
        assert login_res.status_code == 200
        assert login_res.json()["user"]["email"] == "alice@example.com"

        # 4. Log in with email
        login_email = await client.post("/api/v1/auth/login", json={
            "email_or_handle": "alice@example.com",
            "password": "SecurePassword123!"
        })
        assert login_email.status_code == 200

        # 5. Reject wrong password
        login_fail = await client.post("/api/v1/auth/login", json={
            "email_or_handle": "alice",
            "password": "WrongPassword!"
        })
        assert login_fail.status_code == 401

        # 6. Check /me endpoint with cookie
        me_res = await client.get("/api/v1/auth/me", cookies=login_res.cookies)
        assert me_res.status_code == 200
        assert me_res.json()["handle"] == "alice"

        # 7. Check user lookup by handle
        lookup_res = await client.get("/api/v1/auth/users/by-handle/alice", cookies=login_res.cookies)
        assert lookup_res.status_code == 200
        assert lookup_res.json()["full_name"] == "Alice Sharma"

        # 8. Check logout
        logout_res = await client.post("/api/v1/auth/logout", cookies=login_res.cookies)
        assert logout_res.status_code == 200
