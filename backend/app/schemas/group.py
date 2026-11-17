from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime

class ParticipantResponse(BaseModel):
    id: str
    user_id: str
    handle: str
    full_name: str
    vpa: str
    allocated_share_paise: int
    share_percentage: float
    approval_status: str
    lock_id: Optional[str] = None
    reapproval_needed: bool
    declined_reason: Optional[str] = None
    approved_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

class GroupItemResponse(BaseModel):
    id: str
    product_id: str
    title: str
    unit_price_paise: int
    quantity: int
    line_total_paise: int

    model_config = {"from_attributes": True}

class GroupPurchaseResponse(BaseModel):
    id: str
    host_user_id: str
    host_handle: str
    title: str
    status: str
    strategy: str
    split_type: str
    subtotal_paise: int
    tax_paise: int
    delivery_fee_paise: int
    total_paise: int
    checkout_mode: str
    order_id: Optional[str] = None
    failure_reason: Optional[str] = None
    items: List[GroupItemResponse]
    participants: List[ParticipantResponse]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class CreateGroupRequest(BaseModel):
    title: Optional[str] = "Collaborative Group Purchase"
    strategy: Optional[str] = "LOCK"
    split_type: Optional[str] = "EQUAL"
    participant_handles: List[str] = Field(..., min_length=1, description="Handles of co-purchasers (without @)")
    custom_shares_paise: Optional[Dict[str, int]] = None  # handle -> paise

class ParticipantApprovalRequest(BaseModel):
    pin: str = Field(..., min_length=4, max_length=6, description="UPI PIN for SimBank authorization")

class ParticipantDeclineRequest(BaseModel):
    reason: Optional[str] = Field(default="Participant opted out", max_length=200)

class ResplitProposal(BaseModel):
    group_id: str
    status: str
    total_paise: int
    active_participants_count: int
    declined_participants: List[str]
    proposed_allocations: Dict[str, int]  # handle -> new share in paise
    explanation: str
