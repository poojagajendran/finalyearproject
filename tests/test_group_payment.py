import pytest
import httpx
from fastapi import HTTPException
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from backend.app.core.database import Base, get_db
from backend.app.main import app
from backend.app.services.catalog_seed import seed_initial_catalog
from backend.app.services.payment_client import payment_client
from simbank.app.core.database import BankBase, get_bank_db
from simbank.app.main import bank_app
from simbank.app.services.bank_service import seed_bank_accounts

# In-memory database engines
SHOPCART_DB_URL = "sqlite+aiosqlite:///:memory:"
SIMBANK_DB_URL = "sqlite+aiosqlite:///:memory:"

shop_engine = create_async_engine(SHOPCART_DB_URL, connect_args={"check_same_thread": False})
bank_engine = create_async_engine(SIMBANK_DB_URL, connect_args={"check_same_thread": False})

ShopSession = async_sessionmaker(bind=shop_engine, class_=AsyncSession, expire_on_commit=False)
BankSession = async_sessionmaker(bind=bank_engine, class_=AsyncSession, expire_on_commit=False)

async def override_shop_db():
    async with ShopSession() as session:
        yield session

async def override_bank_db():
    async with BankSession() as session:
        yield session

app.dependency_overrides[get_db] = override_shop_db
bank_app.dependency_overrides[get_bank_db] = override_bank_db

@pytest.fixture(autouse=True)
async def setup_dual_databases():
    # Setup ShopCart DB
    async with shop_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with ShopSession() as s:
        await seed_initial_catalog(s)

    # Setup SimBank DB
    async with bank_engine.begin() as conn:
        await conn.run_sync(BankBase.metadata.create_all)
    async with BankSession() as bs:
        await seed_bank_accounts(bs)

    # Route payment_client HTTP calls directly to bank_app in-memory ASGI transport
    payment_client.transport = ASGITransport(app=bank_app)
    payment_client.base_url = "http://simbank"

    yield

    payment_client.transport = None
    async with shop_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    async with bank_engine.begin() as conn:
        await conn.run_sync(BankBase.metadata.drop_all)

@pytest.mark.asyncio
async def test_full_group_purchase_state_machine():
    """Tests DRAFT -> COLLECTING -> COMMITTING -> CONFIRMED"""
    shop_transport = ASGITransport(app=app)
    async with AsyncClient(transport=shop_transport, base_url="http://shopcart") as client:
        # 1. Register Alice, Ravi, Meena
        res_alice = await client.post("/api/v1/auth/register", json={
            "handle": "alice", "email": "alice@test.com", "full_name": "Alice Sharma", "password": "Password123!"
        })
        token_alice = res_alice.json()["access_token"]
        headers_alice = {"Authorization": f"Bearer {token_alice}"}

        res_ravi = await client.post("/api/v1/auth/register", json={
            "handle": "ravi", "email": "ravi@test.com", "full_name": "Ravi Kumar", "password": "Password123!"
        })
        token_ravi = res_ravi.json()["access_token"]
        headers_ravi = {"Authorization": f"Bearer {token_ravi}"}

        res_meena = await client.post("/api/v1/auth/register", json={
            "handle": "meena", "email": "meena@test.com", "full_name": "Meena Patel", "password": "Password123!"
        })
        token_meena = res_meena.json()["access_token"]
        headers_meena = {"Authorization": f"Bearer {token_meena}"}

        # 2. Alice adds earbuds (₹1,999 = 199900 paise) to her cart
        prod_res = await client.get("/api/v1/products?search=earbuds")
        product = prod_res.json()[0]

        await client.post("/api/v1/cart/items", json={
            "product_id": product["id"],
            "quantity": 1
        }, headers=headers_alice)

        # 3. Alice initiates group purchase with Ravi and Meena
        grp_res = await client.post("/api/v1/groups", json={
            "title": "Group Purchase - Earbuds",
            "participant_handles": ["ravi", "meena"],
            "split_type": "EQUAL"
        }, headers=headers_alice)
        assert grp_res.status_code == 201
        group = grp_res.json()
        group_id = group["id"]
        assert group["status"] == "COLLECTING"
        assert len(group["participants"]) == 3

        # Check total paise and exact integer split sum
        total_paise = group["total_paise"]
        shares_sum = sum(p["allocated_share_paise"] for p in group["participants"])
        assert shares_sum == total_paise

        # 4. Alice approves her share with PIN
        appr_alice = await client.post(f"/api/v1/groups/{group_id}/approve", json={"pin": "1234"}, headers=headers_alice)
        assert appr_alice.status_code == 200
        alice_data = appr_alice.json()
        assert alice_data["status"] == "COLLECTING"
        p_alice = next(p for p in alice_data["participants"] if p["handle"] == "alice")
        assert p_alice["approval_status"] == "LOCKED"

        # 5. Ravi approves his share
        appr_ravi = await client.post(f"/api/v1/groups/{group_id}/approve", json={"pin": "1234"}, headers=headers_ravi)
        assert appr_ravi.status_code == 200
        ravi_data = appr_ravi.json()
        assert ravi_data["status"] == "COLLECTING"

        # 6. Meena approves her share -> TRIGGERS AUTOMATIC ATOMIC COMMIT!
        appr_meena = await client.post(f"/api/v1/groups/{group_id}/approve", json={"pin": "1234"}, headers=headers_meena)
        assert appr_meena.status_code == 200
        final_data = appr_meena.json()

        # All 3 approved -> group transitioned to CONFIRMED!
        assert final_data["status"] == "CONFIRMED"
        assert final_data["order_id"].startswith("ORD-")
        for p in final_data["participants"]:
            assert p["approval_status"] == "DEBITED"

@pytest.mark.asyncio
async def test_participant_decline_and_dynamic_redistribution():
    """Tests COLLECTING -> DECLINE -> RESPLIT_PENDING -> REDISTRIBUTE -> COLLECTING -> CONFIRMED"""
    shop_transport = ASGITransport(app=app)
    async with AsyncClient(transport=shop_transport, base_url="http://shopcart") as client:
        # Register Alice, Ravi, Meena
        res_alice = await client.post("/api/v1/auth/register", json={
            "handle": "alice", "email": "alice2@test.com", "full_name": "Alice Sharma", "password": "Password123!"
        })
        token_alice = res_alice.json()["access_token"]
        headers_alice = {"Authorization": f"Bearer {token_alice}"}

        res_ravi = await client.post("/api/v1/auth/register", json={
            "handle": "ravi", "email": "ravi2@test.com", "full_name": "Ravi Kumar", "password": "Password123!"
        })
        token_ravi = res_ravi.json()["access_token"]
        headers_ravi = {"Authorization": f"Bearer {token_ravi}"}

        res_meena = await client.post("/api/v1/auth/register", json={
            "handle": "meena", "email": "meena2@test.com", "full_name": "Meena Patel", "password": "Password123!"
        })
        token_meena = res_meena.json()["access_token"]
        headers_meena = {"Authorization": f"Bearer {token_meena}"}

        # Alice creates group
        prod_res = await client.get("/api/v1/products?search=earbuds")
        product = prod_res.json()[0]
        await client.post("/api/v1/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=headers_alice)

        grp_res = await client.post("/api/v1/groups", json={
            "title": "Group Earbuds Order",
            "participant_handles": ["ravi", "meena"]
        }, headers=headers_alice)
        group_id = grp_res.json()["id"]

        # Alice approves her share
        await client.post(f"/api/v1/groups/{group_id}/approve", json={"pin": "1234"}, headers=headers_alice)

        # Ravi declines!
        dec_res = await client.post(f"/api/v1/groups/{group_id}/decline", json={
            "reason": "Changed my mind"
        }, headers=headers_ravi)
        assert dec_res.status_code == 200
        dec_data = dec_res.json()
        assert dec_data["status"] == "RESPLIT_PENDING"

        # Check proposal
        prop_res = await client.get(f"/api/v1/groups/{group_id}/resplit-proposal", headers=headers_alice)
        assert prop_res.status_code == 200
        prop = prop_res.json()
        assert prop["active_participants_count"] == 2
        assert "ravi" in prop["declined_participants"]

        # Host (Alice) confirms dynamic resplit
        resplit_res = await client.post(f"/api/v1/groups/{group_id}/apply-resplit", headers=headers_alice)
        assert resplit_res.status_code == 200
        resplit_data = resplit_res.json()
        assert resplit_data["status"] == "COLLECTING"

        # Verify Alice's share changed and explicit consent is required
        p_alice = next(p for p in resplit_data["participants"] if p["handle"] == "alice")
        assert p_alice["reapproval_needed"] is True
        assert p_alice["approval_status"] == "PENDING"

        # Both Alice and Meena re-approve their revised shares
        await client.post(f"/api/v1/groups/{group_id}/approve", json={"pin": "1234"}, headers=headers_alice)
        final_res = await client.post(f"/api/v1/groups/{group_id}/approve", json={"pin": "1234"}, headers=headers_meena)
        assert final_res.status_code == 200
        final_group = final_res.json()
        assert final_group["status"] == "CONFIRMED"

@pytest.mark.asyncio
async def test_compensating_refund_saga_recovery(monkeypatch):
    """
    Tests COMMITTING -> Failure on 2nd debit -> COMPENSATING -> SAGA Refund -> ABORTED
    Ensures zero trapped funds when an unexpected failure occurs mid-commit.
    """
    shop_transport = ASGITransport(app=app)
    async with AsyncClient(transport=shop_transport, base_url="http://shopcart") as client:
        # Register Alice and Ravi with valid SimBank VPAs
        res_alice = await client.post("/api/v1/auth/register", json={
            "handle": "alice_saga", "email": "alice_saga@test.com", "full_name": "Alice Sharma", "password": "Password123!", "vpa": "alice@simbank"
        })
        token_alice = res_alice.json()["access_token"]
        headers_alice = {"Authorization": f"Bearer {token_alice}"}

        res_ravi = await client.post("/api/v1/auth/register", json={
            "handle": "ravi_saga", "email": "ravi_saga@test.com", "full_name": "Ravi Kumar", "password": "Password123!", "vpa": "ravi@simbank"
        })
        token_ravi = res_ravi.json()["access_token"]
        headers_ravi = {"Authorization": f"Bearer {token_ravi}"}

        # Alice creates group
        prod_res = await client.get("/api/v1/products?search=earbuds")
        product = prod_res.json()[0]
        await client.post("/api/v1/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=headers_alice)

        grp_res = await client.post("/api/v1/groups", json={
            "title": "Group Purchase with Failure",
            "participant_handles": ["ravi_saga"]
        }, headers=headers_alice)
        group_id = grp_res.json()["id"]

        # Alice approves her share
        await client.post(f"/api/v1/groups/{group_id}/approve", json={"pin": "1234"}, headers=headers_alice)

        # Inject failure: when Ravi's debit is executed, SimBank debit throws an HTTP 400 error!
        real_debit = payment_client.debit_funds
        call_count = {"count": 0}

        async def faulty_debit(*args, **kwargs):
            call_count["count"] += 1
            if call_count["count"] >= 2:
                raise HTTPException(status_code=400, detail="Simulated bank debit failure during commit")
            return await real_debit(*args, **kwargs)

        monkeypatch.setattr(payment_client, "debit_funds", faulty_debit)

        # Ravi approves his share -> triggers commit -> 1st debit succeeds, 2nd fails -> triggers COMPENSATING!
        appr_ravi = await client.post(f"/api/v1/groups/{group_id}/approve", json={"pin": "1234"}, headers=headers_ravi)
        assert appr_ravi.status_code == 200
        aborted_group = appr_ravi.json()

        # Group must be safely ABORTED with failure reason
        assert aborted_group["status"] == "ABORTED"
        assert "Simulated bank debit failure" in aborted_group["failure_reason"]

        # Alice (who was debited first) must have received a compensating refund!
        p_alice = next(p for p in aborted_group["participants"] if p["handle"] == "alice_saga")
        assert p_alice["approval_status"] == "REFUNDED"
