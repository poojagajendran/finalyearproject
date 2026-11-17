import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, Text, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from simbank.app.core.database import BankBase

class BankAccount(BankBase):
    __tablename__ = "bank_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    vpa: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    account_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    account_holder: Mapped[str] = mapped_column(String(100), nullable=False)
    hashed_pin: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Financial balances stored strictly in integer paise
    balance_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    holds: Mapped[list["BankHold"]] = relationship("BankHold", back_populates="account")
    transactions: Mapped[list["BankTransaction"]] = relationship("BankTransaction", back_populates="account")

    @property
    def available_paise(self) -> int:
        return max(0, self.balance_paise - self.locked_paise)

class BankHold(BankBase):
    __tablename__ = "bank_holds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("bank_accounts.id"), nullable=False, index=True)
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    
    # ACTIVE, DEBITED, RELEASED, EXPIRED
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    account: Mapped["BankAccount"] = relationship("BankAccount", back_populates="holds")

class BankTransaction(BankBase):
    __tablename__ = "bank_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("bank_accounts.id"), nullable=False, index=True)
    hold_id: Mapped[str] = mapped_column(String(36), nullable=True)
    reference_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    
    # DEBIT, CREDIT, REFUND
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="SUCCESS", nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    account: Mapped["BankAccount"] = relationship("BankAccount", back_populates="transactions")

class BankWebhookLog(BankBase):
    __tablename__ = "bank_webhook_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    signature: Mapped[str] = mapped_column(String(64), nullable=False)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
