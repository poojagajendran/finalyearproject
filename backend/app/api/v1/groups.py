from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload
from backend.app.core.database import get_db
from backend.app.models.user import User
from backend.app.models.group import GroupPurchase, GroupParticipant, GroupState
from backend.app.schemas.group import (
    CreateGroupRequest, GroupPurchaseResponse,
    ParticipantApprovalRequest, ParticipantDeclineRequest,
    ResplitProposal
)
from backend.app.api.deps import get_current_user
from backend.app.services.group_service import (
    create_group_from_cart, get_group_purchase,
    approve_participant_share, decline_participant_share,
    propose_dynamic_resplit, apply_dynamic_resplit, abort_group_purchase
)

router = APIRouter(prefix="/groups", tags=["Group Purchases & Collaborative Payments"])

def serialize_group(group: GroupPurchase) -> GroupPurchaseResponse:
    """Helper to serialize GroupPurchase with host handle and participants"""
    return GroupPurchaseResponse(
        id=group.id,
        host_user_id=group.host_user_id,
        host_handle=group.host.handle,
        title=group.title,
        status=group.status,
        strategy=group.strategy,
        split_type=group.split_type,
        subtotal_paise=group.subtotal_paise,
        tax_paise=group.tax_paise,
        delivery_fee_paise=group.delivery_fee_paise,
        total_paise=group.total_paise,
        checkout_mode=group.checkout_mode,
        order_id=group.order_id,
        failure_reason=group.failure_reason,
        items=[
            {
                "id": it.id,
                "product_id": it.product_id,
                "title": it.title,
                "unit_price_paise": it.unit_price_paise,
                "quantity": it.quantity,
                "line_total_paise": it.line_total_paise
            }
            for it in group.items
        ],
        participants=[
            {
                "id": p.id,
                "user_id": p.user_id,
                "handle": p.user.handle,
                "full_name": p.user.full_name,
                "vpa": p.vpa,
                "allocated_share_paise": p.allocated_share_paise,
                "share_percentage": p.share_percentage,
                "approval_status": p.approval_status,
                "lock_id": p.lock_id,
                "reapproval_needed": p.reapproval_needed,
                "declined_reason": p.declined_reason,
                "approved_at": p.approved_at
            }
            for p in group.participants
        ],
        created_at=group.created_at,
        updated_at=group.updated_at
    )

@router.post("", response_model=GroupPurchaseResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    req: CreateGroupRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Initiates a collaborative group purchase using current cart items"""
    group = await create_group_from_cart(db, current_user, req)
    return serialize_group(group)

@router.get("/active", response_model=List[GroupPurchaseResponse])
async def list_user_groups(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List active group purchases where the current user is host or participant"""
    stmt = (
        select(GroupPurchase)
        .join(GroupParticipant, GroupPurchase.id == GroupParticipant.group_id)
        .where(
            or_(
                GroupPurchase.host_user_id == current_user.id,
                GroupParticipant.user_id == current_user.id
            )
        )
        .distinct()
        .options(
            selectinload(GroupPurchase.items).selectinload(GroupItem.product),
            selectinload(GroupPurchase.participants).selectinload(GroupParticipant.user),
            selectinload(GroupPurchase.host)
        )
        .order_by(GroupPurchase.created_at.desc())
    )
    res = await db.execute(stmt)
    groups = res.scalars().all()
    return [serialize_group(g) for g in groups]

@router.get("/{group_id}", response_model=GroupPurchaseResponse)
async def get_group_details(
    group_id: str,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Fetch group payment status, participants progress, and item breakdown"""
    group = await get_group_purchase(db, group_id)
    return serialize_group(group)

@router.post("/{group_id}/approve", response_model=GroupPurchaseResponse)
async def approve_share(
    group_id: str,
    req: ParticipantApprovalRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Human enters PIN to authorize funds lock for their allocated share"""
    group = await approve_participant_share(db, group_id, current_user, req.pin)
    return serialize_group(group)

@router.post("/{group_id}/decline", response_model=GroupPurchaseResponse)
async def decline_share(
    group_id: str,
    req: ParticipantDeclineRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Participant declines share, triggering dynamic redistribution (RESPLIT_PENDING)"""
    group = await decline_participant_share(db, group_id, current_user, req.reason)
    return serialize_group(group)

@router.get("/{group_id}/resplit-proposal", response_model=ResplitProposal)
async def get_resplit_proposal(
    group_id: str,
    _: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Fetch dynamic redistribution calculation for remaining participants"""
    return await propose_dynamic_resplit(db, group_id)

@router.post("/{group_id}/apply-resplit", response_model=GroupPurchaseResponse)
async def confirm_resplit(
    group_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Host confirms redistribution, returning group to COLLECTING and requiring participant reapprovals"""
    group = await apply_dynamic_resplit(db, group_id, current_user)
    return serialize_group(group)

@router.post("/{group_id}/abort", response_model=GroupPurchaseResponse)
async def abort_group(
    group_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Host cancels group purchase, safely releasing all authorized bank holds"""
    group = await abort_group_purchase(db, group_id, current_user)
    return serialize_group(group)
