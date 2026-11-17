import uuid
from enum import Enum
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, Boolean, Text, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.core.database import Base

class GroupState(str, Enum):
    DRAFT = "DRAFT"
    COLLECTING = "COLLECTING"
    RESPLIT_PENDING = "RESPLIT_PENDING"
    COMMITTING = "COMMITTING"
    CONFIRMED = "CONFIRMED"
    COMPENSATING = "COMPENSATING"
    ABORTING = "ABORTING"
    ABORTED = "ABORTED"

class PaymentStrategy(str, Enum):
    LOCK = "LOCK"
    WALLET = "WALLET"
    NAIVE = "NAIVE"

class SplitType(str, Enum):
    EQUAL = "EQUAL"
    CUSTOM = "CUSTOM"

class ParticipantStatus(str, Enum):
    PENDING = "PENDING"
    LOCKED = "LOCKED"
    DECLINED = "DECLINED"
    DEBITED = "DEBITED"
    REFUNDED = "REFUNDED"
    RELEASED = "RELEASED"

class GroupPurchase(Base):
    __tablename__ = "group_purchases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    host_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), default="Collaborative Group Order", nullable=False)
    
    # 8 Validated State Machine States
    status: Mapped[str] = mapped_column(String(30), default=GroupState.DRAFT.value, nullable=False, index=True)
    strategy: Mapped[str] = mapped_column(String(20), default=PaymentStrategy.LOCK.value, nullable=False)
    split_type: Mapped[str] = mapped_column(String(20), default=SplitType.EQUAL.value, nullable=False)
    
    # All monetary amounts strictly in integer paise
    subtotal_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tax_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    delivery_fee_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    checkout_mode: Mapped[str] = mapped_column(String(20), default="MANUAL", nullable=False)  # MANUAL or AI_ASSISTED
    order_id: Mapped[str] = mapped_column(String(36), nullable=True)
    failure_reason: Mapped[str] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # Optimistic concurrency
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    host: Mapped["User"] = relationship("User", foreign_keys=[host_user_id], lazy="selectin")
    items: Mapped[list["GroupItem"]] = relationship("GroupItem", back_populates="group", cascade="all, delete-orphan", lazy="selectin")
    participants: Mapped[list["GroupParticipant"]] = relationship("GroupParticipant", back_populates="group", cascade="all, delete-orphan", lazy="selectin")
    operations: Mapped[list["PaymentProviderOperation"]] = relationship("PaymentProviderOperation", back_populates="group", cascade="all, delete-orphan", lazy="selectin")

class GroupItem(Base):
    __tablename__ = "group_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("group_purchases.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("products.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    unit_price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    line_total_paise: Mapped[int] = mapped_column(Integer, nullable=False)

    group: Mapped["GroupPurchase"] = relationship("GroupPurchase", back_populates="items")
    product: Mapped["Product"] = relationship("Product", lazy="selectin")

class GroupParticipant(Base):
    __tablename__ = "group_participants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("group_purchases.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    vpa: Mapped[str] = mapped_column(String(100), nullable=False)
    
    allocated_share_paise: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    share_percentage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    
    # Participant status: PENDING, LOCKED, DECLINED, DEBITED, REFUNDED, RELEASED
    approval_status: Mapped[str] = mapped_column(String(20), default=ParticipantStatus.PENDING.value, nullable=False)
    
    # Financial provider tracking
    lock_id: Mapped[str] = mapped_column(String(36), nullable=True)
    lock_idempotency_key: Mapped[str] = mapped_column(String(100), nullable=True)
    debit_transaction_id: Mapped[str] = mapped_column(String(36), nullable=True)
    debit_idempotency_key: Mapped[str] = mapped_column(String(100), nullable=True)
    refund_transaction_id: Mapped[str] = mapped_column(String(36), nullable=True)
    
    reapproval_needed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    declined_reason: Mapped[str] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    group: Mapped["GroupPurchase"] = relationship("GroupPurchase", back_populates="participants")
    user: Mapped["User"] = relationship("User", lazy="selectin")

class PaymentProviderOperation(Base):
    __tablename__ = "payment_provider_operations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("group_purchases.id", ondelete="CASCADE"), nullable=False, index=True)
    participant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    
    # LOCK, DEBIT, RELEASE, REFUND
    operation_type: Mapped[str] = mapped_column(String(20), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # PENDING, SUCCESS, FAILED, TIMEOUT
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    external_reference: Mapped[str] = mapped_column(String(100), nullable=True)
    request_payload: Mapped[str] = mapped_column(Text, nullable=True)
    response_payload: Mapped[str] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    group: Mapped["GroupPurchase"] = relationship("GroupPurchase", back_populates="operations")
