from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from simbank.app.core.database import get_bank_db
from simbank.app.models.bank import BankAccount, BankHold, BankTransaction
from simbank.app.schemas.bank import (
    BankAccountResponse,
    LockFundsRequest, LockFundsResponse,
    DebitFundsRequest, DebitFundsResponse,
    ReleaseFundsRequest, ReleaseFundsResponse,
    RefundFundsRequest, RefundFundsResponse
)
from simbank.app.services.bank_service import (
    lock_funds, debit_funds, release_funds, refund_funds
)
from simbank.app.services.webhook_dispatcher import dispatch_webhook

router = APIRouter(prefix="/bank", tags=["SimBank Financial Engine"])

@router.get("/accounts/{vpa}", response_model=BankAccountResponse)
async def get_account_status(vpa: str, db: AsyncSession = Depends(get_bank_db)):
    """Fetch bank account balance and hold status by VPA"""
    clean_vpa = vpa.lower().strip()
    result = await db.execute(select(BankAccount).where(BankAccount.vpa == clean_vpa))
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"VPA '{clean_vpa}' not found."
        )
    return BankAccountResponse(
        id=account.id,
        vpa=account.vpa,
        account_number=account.account_number,
        account_holder=account.account_holder,
        balance_paise=account.balance_paise,
        locked_paise=account.locked_paise,
        available_paise=account.available_paise,
        is_active=account.is_active
    )

@router.post("/locks", response_model=LockFundsResponse, status_code=status.HTTP_201_CREATED)
async def api_lock_funds(req: LockFundsRequest, db: AsyncSession = Depends(get_bank_db)):
    """
    Simulates VPA funds-lock.
    Locks amount from available balance into hold while maintaining funds in user's bank account.
    """
    res = await lock_funds(db, req)
    
    # Asynchronously dispatch signed webhook
    await dispatch_webhook(
        db=db,
        event_type="FUNDS_LOCKED",
        reference_id=req.reference_id,
        payload={
            "lock_id": res.lock_id,
            "vpa": res.vpa,
            "amount_paise": res.amount_paise,
            "reference_id": res.reference_id,
            "status": res.status
        }
    )
    return res

@router.post("/debits", response_model=DebitFundsResponse)
async def api_debit_funds(req: DebitFundsRequest, db: AsyncSession = Depends(get_bank_db)):
    """Capture/debit previously locked funds"""
    res = await debit_funds(db, req)
    
    await dispatch_webhook(
        db=db,
        event_type="FUNDS_DEBITED",
        reference_id=req.reference_id,
        payload={
            "transaction_id": res.transaction_id,
            "lock_id": res.lock_id,
            "amount_paise": res.amount_paise,
            "reference_id": req.reference_id,
            "status": res.status
        }
    )
    return res

@router.post("/releases", response_model=ReleaseFundsResponse)
async def api_release_funds(req: ReleaseFundsRequest, db: AsyncSession = Depends(get_bank_db)):
    """Release locked funds back to available balance without debiting"""
    res = await release_funds(db, req)
    
    await dispatch_webhook(
        db=db,
        event_type="FUNDS_RELEASED",
        reference_id=req.lock_id,
        payload={
            "lock_id": res.lock_id,
            "released_amount_paise": res.released_amount_paise,
            "status": res.status
        }
    )
    return res

@router.post("/refunds", response_model=RefundFundsResponse)
async def api_refund_funds(req: RefundFundsRequest, db: AsyncSession = Depends(get_bank_db)):
    """Credit compensating refund back to participant bank account"""
    res = await refund_funds(db, req)
    
    await dispatch_webhook(
        db=db,
        event_type="FUNDS_REFUNDED",
        reference_id=req.reference_id,
        payload={
            "refund_transaction_id": res.refund_transaction_id,
            "vpa": req.vpa,
            "amount_paise": res.amount_paise,
            "reference_id": req.reference_id,
            "status": res.status
        }
    )
    return res

@router.get("/holds/{lock_id}")
async def get_hold_status(lock_id: str, db: AsyncSession = Depends(get_bank_db)):
    """Fetch status of hold for reconciliation and recovery verification"""
    result = await db.execute(select(BankHold).where(BankHold.id == lock_id))
    hold = result.scalar_one_or_none()
    if not hold:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hold not found")
    return {
        "lock_id": hold.id,
        "amount_paise": hold.amount_paise,
        "reference_id": hold.reference_id,
        "status": hold.status,
        "created_at": hold.created_at
    }

@router.get("/transactions/by-key/{idempotency_key}")
async def get_transaction_by_key(idempotency_key: str, db: AsyncSession = Depends(get_bank_db)):
    """Fetch transaction by idempotency key for network timeout reconciliation"""
    result = await db.execute(
        select(BankTransaction).where(BankTransaction.idempotency_key == idempotency_key)
    )
    tx = result.scalar_one_or_none()
    if not tx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return {
        "transaction_id": tx.id,
        "type": tx.type,
        "amount_paise": tx.amount_paise,
        "reference_id": tx.reference_id,
        "status": tx.status,
        "created_at": tx.created_at
    }
