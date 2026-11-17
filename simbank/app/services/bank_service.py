from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status
from simbank.app.models.bank import BankAccount, BankHold, BankTransaction
from simbank.app.schemas.bank import (
    LockFundsRequest, LockFundsResponse,
    DebitFundsRequest, DebitFundsResponse,
    ReleaseFundsRequest, ReleaseFundsResponse,
    RefundFundsRequest, RefundFundsResponse
)
from simbank.app.core.security import hash_pin, verify_pin

DEFAULT_TEST_ACCOUNTS = [
    {"vpa": "alice@simbank", "name": "Alice Sharma", "pin": "1234", "balance": 5000000, "acc": "1001001"},
    {"vpa": "ravi@simbank", "name": "Ravi Kumar", "pin": "1234", "balance": 5000000, "acc": "1001002"},
    {"vpa": "meena@simbank", "name": "Meena Patel", "pin": "1234", "balance": 5000000, "acc": "1001003"},
    {"vpa": "kiran@simbank", "name": "Kiran Rao", "pin": "1234", "balance": 5000000, "acc": "1001004"},
    {"vpa": "broke_user@simbank", "name": "Broke User", "pin": "1234", "balance": 1000, "acc": "1001005"}, # ₹10 only
]

async def seed_bank_accounts(db: AsyncSession) -> None:
    """Seed standard test bank accounts if empty"""
    acc_check = await db.execute(select(BankAccount))
    if not acc_check.first():
        for test_acc in DEFAULT_TEST_ACCOUNTS:
            acc = BankAccount(
                vpa=test_acc["vpa"],
                account_number=test_acc["acc"],
                account_holder=test_acc["name"],
                hashed_pin=hash_pin(test_acc["pin"]),
                balance_paise=test_acc["balance"],
                locked_paise=0
            )
            db.add(acc)
        await db.commit()

async def lock_funds(db: AsyncSession, req: LockFundsRequest) -> LockFundsResponse:
    """
    Simulates VPA funds-lock (Hold/Pre-authorization)
    Guarantees funds are held in user's bank account (LOCK strategy)
    """
    # 1. Idempotency Check
    existing_hold = await db.execute(
        select(BankHold).where(BankHold.idempotency_key == req.idempotency_key)
    )
    hold = existing_hold.scalar_one_or_none()
    if hold:
        return LockFundsResponse(
            lock_id=hold.id,
            status=hold.status,
            amount_paise=hold.amount_paise,
            vpa=req.vpa,
            reference_id=hold.reference_id,
            created_at=hold.created_at
        )

    # 2. Account verification
    acc_res = await db.execute(select(BankAccount).where(BankAccount.vpa == req.vpa.lower()))
    account = acc_res.scalar_one_or_none()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bank account with VPA '{req.vpa}' not found in SimBank."
        )

    # 3. PIN verification
    if not verify_pin(req.pin, account.hashed_pin):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid UPI PIN. Authorization failed."
        )

    # 4. Solvency check
    if account.available_paise < req.amount_paise:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient funds. Required: ₹{req.amount_paise/100:.2f}, Available: ₹{account.available_paise/100:.2f}"
        )

    # 5. Lock funds atomically
    account.locked_paise += req.amount_paise
    new_hold = BankHold(
        idempotency_key=req.idempotency_key,
        account_id=account.id,
        amount_paise=req.amount_paise,
        reference_id=req.reference_id,
        status="ACTIVE"
    )
    db.add(new_hold)
    await db.commit()
    await db.refresh(new_hold)

    return LockFundsResponse(
        lock_id=new_hold.id,
        status=new_hold.status,
        amount_paise=new_hold.amount_paise,
        vpa=req.vpa,
        reference_id=new_hold.reference_id,
        created_at=new_hold.created_at
    )

async def debit_funds(db: AsyncSession, req: DebitFundsRequest) -> DebitFundsResponse:
    """
    Debits / captures previously locked funds.
    Decrements both balance and locked hold.
    """
    # 1. Idempotency Check
    existing_tx = await db.execute(
        select(BankTransaction).where(BankTransaction.idempotency_key == req.idempotency_key)
    )
    tx = existing_tx.scalar_one_or_none()
    if tx:
        hold_res = await db.execute(select(BankHold).where(BankHold.id == req.lock_id))
        hold = hold_res.scalar_one_or_none()
        acc_res = await db.execute(select(BankAccount).where(BankAccount.id == tx.account_id))
        acc = acc_res.scalar_one_or_none()
        return DebitFundsResponse(
            transaction_id=tx.id,
            lock_id=req.lock_id,
            status=tx.status,
            amount_paise=tx.amount_paise,
            remaining_balance_paise=acc.balance_paise if acc else 0
        )

    # 2. Verify Hold
    hold_res = await db.execute(select(BankHold).where(BankHold.id == req.lock_id))
    hold = hold_res.scalar_one_or_none()
    if not hold:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hold lock not found.")

    if hold.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot debit hold in '{hold.status}' status."
        )

    # 3. Verify Account
    acc_res = await db.execute(select(BankAccount).where(BankAccount.id == hold.account_id))
    account = acc_res.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")

    # 4. Atomic settlement
    account.balance_paise -= req.amount_paise
    account.locked_paise -= req.amount_paise
    hold.status = "DEBITED"

    new_tx = BankTransaction(
        idempotency_key=req.idempotency_key,
        account_id=account.id,
        hold_id=hold.id,
        reference_id=req.reference_id,
        type="DEBIT",
        amount_paise=req.amount_paise,
        status="SUCCESS",
        description=f"Group purchase debit for {req.reference_id}"
    )
    db.add(new_tx)
    await db.commit()
    await db.refresh(new_tx)

    return DebitFundsResponse(
        transaction_id=new_tx.id,
        lock_id=hold.id,
        status="SUCCESS",
        amount_paise=req.amount_paise,
        remaining_balance_paise=account.balance_paise
    )

async def release_funds(db: AsyncSession, req: ReleaseFundsRequest) -> ReleaseFundsResponse:
    """
    Releases locked funds back to available balance without debiting.
    Used for cancellations, declined participants, or resplits.
    """
    hold_res = await db.execute(select(BankHold).where(BankHold.id == req.lock_id))
    hold = hold_res.scalar_one_or_none()
    if not hold:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hold lock not found.")

    if hold.status == "RELEASED":
        # Idempotent release
        return ReleaseFundsResponse(
            lock_id=hold.id,
            status="RELEASED",
            released_amount_paise=hold.amount_paise
        )

    if hold.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot release hold in '{hold.status}' state."
        )

    acc_res = await db.execute(select(BankAccount).where(BankAccount.id == hold.account_id))
    account = acc_res.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")

    # Decrement locked funds, restoring available balance
    account.locked_paise = max(0, account.locked_paise - hold.amount_paise)
    hold.status = "RELEASED"
    await db.commit()

    return ReleaseFundsResponse(
        lock_id=hold.id,
        status="RELEASED",
        released_amount_paise=hold.amount_paise
    )

async def refund_funds(db: AsyncSession, req: RefundFundsRequest) -> RefundFundsResponse:
    """
    Compensating refund credited back to participant account.
    Used when a multi-user purchase fails midway during the commit phase.
    """
    # 1. Idempotency Check
    existing_tx = await db.execute(
        select(BankTransaction).where(BankTransaction.idempotency_key == req.idempotency_key)
    )
    tx = existing_tx.scalar_one_or_none()
    if tx:
        acc_res = await db.execute(select(BankAccount).where(BankAccount.id == tx.account_id))
        acc = acc_res.scalar_one_or_none()
        return RefundFundsResponse(
            refund_transaction_id=tx.id,
            status=tx.status,
            amount_paise=tx.amount_paise,
            new_balance_paise=acc.balance_paise if acc else 0
        )

    acc_res = await db.execute(select(BankAccount).where(BankAccount.vpa == req.vpa.lower()))
    account = acc_res.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"VPA '{req.vpa}' not found.")

    account.balance_paise += req.amount_paise
    new_tx = BankTransaction(
        idempotency_key=req.idempotency_key,
        account_id=account.id,
        reference_id=req.reference_id,
        type="REFUND",
        amount_paise=req.amount_paise,
        status="SUCCESS",
        description=f"Compensating refund: {req.reason}"
    )
    db.add(new_tx)
    await db.commit()
    await db.refresh(new_tx)

    return RefundFundsResponse(
        refund_transaction_id=new_tx.id,
        status="SUCCESS",
        amount_paise=req.amount_paise,
        new_balance_paise=account.balance_paise
    )
