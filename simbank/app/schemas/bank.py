from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class BankAccountCreate(BaseModel):
    vpa: str = Field(..., pattern=r"^[a-zA-Z0-9_\.\-]+@[a-zA-Z0-9]+$")
    account_holder: str
    pin: str = Field(..., min_length=4, max_length=6)
    initial_balance_paise: int = Field(default=5000000, ge=0)  # Default ₹50,000.00

class BankAccountResponse(BaseModel):
    id: str
    vpa: str
    account_number: str
    account_holder: str
    balance_paise: int
    locked_paise: int
    available_paise: int
    is_active: bool

    model_config = {"from_attributes": True}

class LockFundsRequest(BaseModel):
    vpa: str
    pin: str
    amount_paise: int = Field(..., gt=0)
    reference_id: str
    idempotency_key: str

class LockFundsResponse(BaseModel):
    lock_id: str
    status: str
    amount_paise: int
    vpa: str
    reference_id: str
    created_at: datetime

    model_config = {"from_attributes": True}

class DebitFundsRequest(BaseModel):
    lock_id: str
    amount_paise: int = Field(..., gt=0)
    reference_id: str
    idempotency_key: str

class DebitFundsResponse(BaseModel):
    transaction_id: str
    lock_id: str
    status: str
    amount_paise: int
    remaining_balance_paise: int

class ReleaseFundsRequest(BaseModel):
    lock_id: str
    idempotency_key: str
    reason: Optional[str] = "Cancelled or redistribution"

class ReleaseFundsResponse(BaseModel):
    lock_id: str
    status: str
    released_amount_paise: int

class RefundFundsRequest(BaseModel):
    vpa: str
    amount_paise: int = Field(..., gt=0)
    reference_id: str
    idempotency_key: str
    reason: Optional[str] = "Compensating refund"

class RefundFundsResponse(BaseModel):
    refund_transaction_id: str
    status: str
    amount_paise: int
    new_balance_paise: int
