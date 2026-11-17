import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from simbank.app.core.database import BankBase, get_bank_db
from simbank.app.services.bank_service import seed_bank_accounts
from simbank.app.core.security import generate_signature, verify_signature
from simbank.app.main import bank_app

TEST_BANK_DB_URL = "sqlite+aiosqlite:///:memory:"

test_bank_engine = create_async_engine(
    TEST_BANK_DB_URL,
    connect_args={"check_same_thread": False}
)

TestBankAsyncSessionLocal = async_sessionmaker(
    bind=test_bank_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

async def override_get_bank_db():
    async with TestBankAsyncSessionLocal() as session:
        yield session

bank_app.dependency_overrides[get_bank_db] = override_get_bank_db

@pytest.fixture(autouse=True)
async def setup_bank_test_db():
    async with test_bank_engine.begin() as conn:
        await conn.run_sync(BankBase.metadata.create_all)
    
    async with TestBankAsyncSessionLocal() as session:
        await seed_bank_accounts(session)

    yield

    async with test_bank_engine.begin() as conn:
        await conn.run_sync(BankBase.metadata.drop_all)

@pytest.mark.asyncio
async def test_simbank_operations():
    transport = ASGITransport(app=bank_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Account balance check
        res = await client.get("/api/v1/bank/accounts/alice@simbank")
        assert res.status_code == 200
        data = res.json()
        assert data["vpa"] == "alice@simbank"
        assert data["balance_paise"] == 5000000  # ₹50,000
        assert data["available_paise"] == 5000000

        # 2. Lock with wrong PIN -> 401
        res_wrong_pin = await client.post("/api/v1/bank/locks", json={
            "vpa": "alice@simbank",
            "pin": "9999",
            "amount_paise": 100000,
            "reference_id": "grp_test_1",
            "idempotency_key": "idem_lock_wrong_pin"
        })
        assert res_wrong_pin.status_code == 401
        assert "Invalid UPI PIN" in res_wrong_pin.json()["detail"]

        # 3. Lock with insufficient funds -> 400
        res_broke = await client.post("/api/v1/bank/locks", json={
            "vpa": "broke_user@simbank",
            "pin": "1234",
            "amount_paise": 50000,  # ₹500, but has only ₹10
            "reference_id": "grp_test_broke",
            "idempotency_key": "idem_lock_broke"
        })
        assert res_broke.status_code == 400
        assert "Insufficient funds" in res_broke.json()["detail"]

        # 4. Successful funds lock (LOCK strategy: money stays in account under hold)
        lock_req = {
            "vpa": "alice@simbank",
            "pin": "1234",
            "amount_paise": 200000,  # ₹2,000.00
            "reference_id": "grp_test_alice",
            "idempotency_key": "idem_lock_alice_1"
        }
        res_lock = await client.post("/api/v1/bank/locks", json=lock_req)
        assert res_lock.status_code == 201
        lock_data = res_lock.json()
        lock_id = lock_data["lock_id"]
        assert lock_data["status"] == "ACTIVE"
        assert lock_data["amount_paise"] == 200000

        # Verify Alice's balance: total balance intact (₹50,000), available reduced to ₹48,000
        res_bal = await client.get("/api/v1/bank/accounts/alice@simbank")
        alice_bal = res_bal.json()
        assert alice_bal["balance_paise"] == 5000000
        assert alice_bal["locked_paise"] == 200000
        assert alice_bal["available_paise"] == 4800000

        # 5. Idempotent lock: repeated call with same key returns identical lock without duplicate lock
        res_lock_dup = await client.post("/api/v1/bank/locks", json=lock_req)
        assert res_lock_dup.status_code == 200 or res_lock_dup.status_code == 201
        assert res_lock_dup.json()["lock_id"] == lock_id

        # Balance remains unchanged
        res_bal_after = await client.get("/api/v1/bank/accounts/alice@simbank")
        assert res_bal_after.json()["locked_paise"] == 200000

        # 6. Debit funds
        debit_req = {
            "lock_id": lock_id,
            "amount_paise": 200000,
            "reference_id": "grp_test_alice",
            "idempotency_key": "idem_debit_alice_1"
        }
        res_debit = await client.post("/api/v1/bank/debits", json=debit_req)
        assert res_debit.status_code == 200
        debit_data = res_debit.json()
        assert debit_data["status"] == "SUCCESS"
        assert debit_data["remaining_balance_paise"] == 4800000

        # 7. Release lock test on another hold
        res_lock2 = await client.post("/api/v1/bank/locks", json={
            "vpa": "ravi@simbank",
            "pin": "1234",
            "amount_paise": 150000,
            "reference_id": "grp_test_ravi",
            "idempotency_key": "idem_lock_ravi_1"
        })
        assert res_lock2.status_code == 201
        ravi_lock_id = res_lock2.json()["lock_id"]

        # Release Ravi's lock
        res_rel = await client.post("/api/v1/bank/releases", json={
            "lock_id": ravi_lock_id,
            "idempotency_key": "idem_rel_ravi_1"
        })
        assert res_rel.status_code == 200
        assert res_rel.json()["status"] == "RELEASED"

        # Ravi's balance is fully restored to 50,000
        ravi_bal = await client.get("/api/v1/bank/accounts/ravi@simbank")
        assert ravi_bal.json()["available_paise"] == 5000000
        assert ravi_bal.json()["locked_paise"] == 0

        # 8. Compensating refund test
        res_ref = await client.post("/api/v1/bank/refunds", json={
            "vpa": "alice@simbank",
            "amount_paise": 200000,
            "reference_id": "grp_test_alice",
            "idempotency_key": "idem_ref_alice_1",
            "reason": "Test SAGA compensation"
        })
        assert res_ref.status_code == 200
        assert res_ref.json()["status"] == "SUCCESS"
        assert res_ref.json()["new_balance_paise"] == 5000000

        # 9. HMAC Webhook signature verification test
        test_payload = b'{"amount_paise":200000,"event_type":"FUNDS_LOCKED"}'
        sig = generate_signature(test_payload, "test-secret")
        assert verify_signature(test_payload, sig, "test-secret") is True
        assert verify_signature(test_payload, "tampered-signature", "test-secret") is False
