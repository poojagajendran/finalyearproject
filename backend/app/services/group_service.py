import uuid
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from backend.app.models.user import User
from backend.app.models.product import CartItem
from backend.app.models.group import (
    GroupPurchase, GroupItem, GroupParticipant, PaymentProviderOperation,
    GroupState, PaymentStrategy, SplitType, ParticipantStatus
)
from backend.app.schemas.group import CreateGroupRequest, ResplitProposal
from backend.app.services.cart_service import calculate_cart_totals
from backend.app.services.split_engine import (
    calculate_equal_split, validate_custom_split, redistribute_shares
)
from backend.app.services.payment_client import payment_client

async def create_group_from_cart(
    db: AsyncSession,
    host_user: User,
    req: CreateGroupRequest
) -> GroupPurchase:
    """Creates a new collaborative group purchase from the host user's cart"""
    # 1. Fetch host's cart items
    cart_stmt = (
        select(CartItem)
        .where(CartItem.user_id == host_user.id)
        .options(selectinload(CartItem.product))
    )
    cart_res = await db.execute(cart_stmt)
    cart_items = cart_res.scalars().all()

    if not cart_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create group purchase: Your cart is empty."
        )

    # 2. Compute cart totals in integer paise
    subtotal, tax, delivery, total = calculate_cart_totals(cart_items)

    # 3. Lookup invited participants
    cleaned_handles = [h.strip().lower().lstrip("@") for h in req.participant_handles if h.strip()]
    if not cleaned_handles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one participant handle is required."
        )

    # Lookup all participants in DB
    users_stmt = select(User).where(User.handle.in_(cleaned_handles))
    users_res = await db.execute(users_stmt)
    invited_users = users_res.scalars().all()

    found_handles = {u.handle for u in invited_users}
    missing_handles = set(cleaned_handles) - found_handles
    if missing_handles:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"The following user handles were not found: {list(missing_handles)}"
        )

    # Participant list includes host + invited users
    all_participants: List[User] = [host_user]
    for u in invited_users:
        if u.id != host_user.id:
            all_participants.append(u)

    participant_ids = [u.id for u in all_participants]

    # 4. Calculate split
    if req.split_type == SplitType.CUSTOM.value and req.custom_shares_paise:
        handle_to_id = {u.handle: u.id for u in all_participants}
        id_shares: Dict[str, int] = {}
        for h, paise in req.custom_shares_paise.items():
            clean_h = h.strip().lower().lstrip("@")
            if clean_h in handle_to_id:
                id_shares[handle_to_id[clean_h]] = paise
        allocations = validate_custom_split(total, id_shares, participant_ids)
    else:
        allocations = calculate_equal_split(total, participant_ids, host_user.id)

    # 5. Create GroupPurchase (status: DRAFT -> COLLECTING)
    group = GroupPurchase(
        host_user_id=host_user.id,
        title=req.title or f"{host_user.full_name}'s Group Order",
        status=GroupState.COLLECTING.value,
        strategy=req.strategy or PaymentStrategy.LOCK.value,
        split_type=req.split_type or SplitType.EQUAL.value,
        subtotal_paise=subtotal,
        tax_paise=tax,
        delivery_fee_paise=delivery,
        total_paise=total,
        checkout_mode="MANUAL"
    )
    db.add(group)
    await db.flush()

    # 6. Attach Group Items
    for ci in cart_items:
        gi = GroupItem(
            group_id=group.id,
            product_id=ci.product_id,
            title=ci.product.title,
            unit_price_paise=ci.product.price_paise,
            quantity=ci.quantity,
            line_total_paise=ci.quantity * ci.product.price_paise
        )
        db.add(gi)

    # 7. Attach Participants
    for u in all_participants:
        share = allocations[u.id]
        pct = round((share / total) * 100, 2)
        gp = GroupParticipant(
            group_id=group.id,
            user_id=u.id,
            vpa=u.vpa,
            allocated_share_paise=share,
            share_percentage=pct,
            approval_status=ParticipantStatus.PENDING.value
        )
        db.add(gp)

    # 8. Clear host cart
    for ci in cart_items:
        await db.delete(ci)

    await db.commit()
    return await get_group_purchase(db, group.id)

async def refresh_group(db: AsyncSession, group: GroupPurchase) -> GroupPurchase:
    """Explicitly refreshes relationships on group instance in current async session"""
    await db.refresh(group, ["items", "participants", "host"])
    for p in group.participants:
        await db.refresh(p, ["user"])
    return group

async def get_group_purchase(db: AsyncSession, group_id: str) -> GroupPurchase:
    """Fetch group purchase with items and participants"""
    stmt = (
        select(GroupPurchase)
        .where(GroupPurchase.id == group_id)
        .options(
            selectinload(GroupPurchase.items).selectinload(GroupItem.product),
            selectinload(GroupPurchase.participants).selectinload(GroupParticipant.user),
            selectinload(GroupPurchase.host)
        )
    )
    res = await db.execute(stmt)
    group = res.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group purchase not found")
    return await refresh_group(db, group)

async def approve_participant_share(
    db: AsyncSession,
    group_id: str,
    current_user: User,
    pin: str
) -> GroupPurchase:
    """
    Participant authorizes their share by entering their PIN.
    SimBank executes funds-lock (LOCK strategy) outside DB transaction.
    """
    group = await get_group_purchase(db, group_id)

    if group.status != GroupState.COLLECTING.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve share: Group is currently in '{group.status}' status (must be COLLECTING)."
        )

    # Find participant record
    participant = next((p for p in group.participants if p.user_id == current_user.id), None)
    if not participant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a registered participant of this group purchase."
        )

    if participant.approval_status == ParticipantStatus.LOCKED.value and not participant.reapproval_needed:
        return group  # Already authorized

    # Idempotency key for SimBank lock operation
    lock_idempotency_key = f"lock_{group.id}_{participant.id}_{participant.allocated_share_paise}"

    # CALL SIMBANK OUTSIDE DB TRANSACTION
    lock_res = await payment_client.lock_funds(
        vpa=participant.vpa,
        pin=pin,
        amount_paise=participant.allocated_share_paise,
        reference_id=group.id,
        idempotency_key=lock_idempotency_key
    )

    # Update participant and record provider operation
    participant.approval_status = ParticipantStatus.LOCKED.value
    participant.lock_id = lock_res["lock_id"]
    participant.lock_idempotency_key = lock_idempotency_key
    participant.reapproval_needed = False
    participant.approved_at = datetime.now(timezone.utc)

    op = PaymentProviderOperation(
        group_id=group.id,
        participant_id=participant.id,
        operation_type="LOCK",
        idempotency_key=lock_idempotency_key,
        amount_paise=participant.allocated_share_paise,
        status="SUCCESS",
        external_reference=lock_res["lock_id"],
        response_payload=str(lock_res)
    )
    db.add(op)
    await db.commit()

    # Check if ALL active participants have locked funds
    all_locked = all(
        p.approval_status == ParticipantStatus.LOCKED.value
        for p in group.participants
        if p.approval_status != ParticipantStatus.DECLINED.value
    )

    if all_locked:
        # Trigger automatic atomic commit!
        return await commit_group_purchase(db, group.id)

    return await get_group_purchase(db, group.id)

async def decline_participant_share(
    db: AsyncSession,
    group_id: str,
    current_user: User,
    reason: Optional[str] = "Opted out"
) -> GroupPurchase:
    """Participant declines share, triggering dynamic redistribution (RESPLIT_PENDING)"""
    group = await get_group_purchase(db, group_id)

    if group.status not in [GroupState.COLLECTING.value, GroupState.RESPLIT_PENDING.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot decline: Group is in '{group.status}' state."
        )

    participant = next((p for p in group.participants if p.user_id == current_user.id), None)
    if not participant:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a participant in this group.")

    # If participant already had an active lock, release it
    if participant.lock_id and participant.approval_status == ParticipantStatus.LOCKED.value:
        rel_key = f"rel_{group.id}_{participant.id}_{participant.lock_id}"
        await payment_client.release_funds(participant.lock_id, rel_key, reason="Participant declined")
        participant.approval_status = ParticipantStatus.RELEASED.value

    participant.approval_status = ParticipantStatus.DECLINED.value
    participant.declined_reason = reason

    # Transition group state to RESPLIT_PENDING
    group.status = GroupState.RESPLIT_PENDING.value
    await db.commit()

    return await get_group_purchase(db, group.id)

async def propose_dynamic_resplit(db: AsyncSession, group_id: str) -> ResplitProposal:
    """Generates dynamic redistribution proposal for remaining active participants"""
    group = await get_group_purchase(db, group_id)

    active_participants = [p for p in group.participants if p.approval_status != ParticipantStatus.DECLINED.value]
    declined_participants = [p.user.handle for p in group.participants if p.approval_status == ParticipantStatus.DECLINED.value]

    if not active_participants:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="All participants have declined. Group purchase must be aborted."
        )

    active_ids = [p.user_id for p in active_participants]
    new_allocations = redistribute_shares(group.total_paise, active_ids, group.host_user_id)

    id_to_handle = {p.user_id: p.user.handle for p in active_participants}
    handle_allocations = {id_to_handle[uid]: paise for uid, paise in new_allocations.items()}

    explanation = (
        f"{len(declined_participants)} participant(s) ({', '.join(declined_participants)}) declined. "
        f"Redistributed total ₹{group.total_paise/100:.2f} equally across remaining {len(active_participants)} participant(s). "
        f"Each remaining participant will pay ₹{list(handle_allocations.values())[0]/100:.2f}."
    )

    return ResplitProposal(
        group_id=group.id,
        status=group.status,
        total_paise=group.total_paise,
        active_participants_count=len(active_participants),
        declined_participants=declined_participants,
        proposed_allocations=handle_allocations,
        explanation=explanation
    )

async def apply_dynamic_resplit(db: AsyncSession, group_id: str, host_user: User) -> GroupPurchase:
    """
    Applies revised split.
    Critical payment rule: Releases old locks for participants whose share changed,
    and requires revised participant consent ('reapproval_needed = True').
    """
    group = await get_group_purchase(db, group_id)

    if group.host_user_id != host_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only group host can confirm redistribution.")

    active_participants = [p for p in group.participants if p.approval_status != ParticipantStatus.DECLINED.value]
    active_ids = [p.user_id for p in active_participants]
    new_allocations = redistribute_shares(group.total_paise, active_ids, group.host_user_id)

    for p in active_participants:
        new_share = new_allocations[p.user_id]
        if new_share != p.allocated_share_paise:
            # If participant was locked, release old lock so new amount can be authorized
            if p.lock_id and p.approval_status == ParticipantStatus.LOCKED.value:
                rel_key = f"rel_resplit_{group.id}_{p.id}_{p.lock_id}"
                await payment_client.release_funds(p.lock_id, rel_key, reason="Redistributed share changed")
                p.lock_id = None

            p.allocated_share_paise = new_share
            p.share_percentage = round((new_share / group.total_paise) * 100, 2)
            p.approval_status = ParticipantStatus.PENDING.value
            p.reapproval_needed = True  # Explicit consent required!

    group.status = GroupState.COLLECTING.value
    await db.commit()
    res_group = await get_group_purchase(db, group.id)
    print(f"DEBUG: res_group.participants count: {len(res_group.participants)}, handles: {[p.user.handle for p in res_group.participants]}")
    return res_group

async def commit_group_purchase(db: AsyncSession, group_id: str) -> GroupPurchase:
    """
    COMMITTING Phase: Atomic two-phase capture.
    Debits all locked participants. If any debit permanently fails, enters COMPENSATING.
    """
    group = await get_group_purchase(db, group_id)
    group.status = GroupState.COMMITTING.value
    await db.commit()

    active_participants = [p for p in group.participants if p.approval_status != ParticipantStatus.DECLINED.value]

    for p in active_participants:
        debit_idempotency_key = f"debit_{group.id}_{p.id}_{p.allocated_share_paise}"
        try:
            debit_res = await payment_client.debit_funds(
                lock_id=p.lock_id,
                amount_paise=p.allocated_share_paise,
                reference_id=group.id,
                idempotency_key=debit_idempotency_key
            )
            p.approval_status = ParticipantStatus.DEBITED.value
            p.debit_transaction_id = debit_res["transaction_id"]
            p.debit_idempotency_key = debit_idempotency_key

            op = PaymentProviderOperation(
                group_id=group.id,
                participant_id=p.id,
                operation_type="DEBIT",
                idempotency_key=debit_idempotency_key,
                amount_paise=p.allocated_share_paise,
                status="SUCCESS",
                external_reference=debit_res["transaction_id"],
                response_payload=str(debit_res)
            )
            db.add(op)
            await db.commit()

        except HTTPException as e:
            # Check for network timeout reconciliation
            if e.status_code == status.HTTP_504_GATEWAY_TIMEOUT:
                reconcile_tx = await payment_client.query_transaction(debit_idempotency_key)
                if reconcile_tx and reconcile_tx.get("status") == "SUCCESS":
                    p.approval_status = ParticipantStatus.DEBITED.value
                    p.debit_transaction_id = reconcile_tx["transaction_id"]
                    await db.commit()
                    continue

            # Permanent debit failure encountered! Trigger SAGA Compensating refunds!
            return await execute_compensating_refunds(
                db=db,
                group_id=group.id,
                failure_reason=f"Debit failed for {p.user.full_name} ({p.vpa}): {e.detail}"
            )

    # All debits succeeded!
    group.status = GroupState.CONFIRMED.value
    group.order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
    await db.commit()
    res_group = await get_group_purchase(db, group.id)
    print(f"DEBUG: res_group.participants count: {len(res_group.participants)}, handles: {[p.user.handle for p in res_group.participants]}")
    return res_group

async def execute_compensating_refunds(
    db: AsyncSession,
    group_id: str,
    failure_reason: str
) -> GroupPurchase:
    """
    SAGA COMPENSATING Phase:
    - Debited participants receive compensating refunds.
    - Locked participants have holds released.
    - Group transitions to ABORTED. Zero trapped funds.
    """
    group = await get_group_purchase(db, group_id)
    group.status = GroupState.COMPENSATING.value
    group.failure_reason = failure_reason
    await db.commit()

    for p in group.participants:
        if p.approval_status == ParticipantStatus.DEBITED.value:
            ref_key = f"refund_{group.id}_{p.id}_{p.allocated_share_paise}"
            ref_res = await payment_client.refund_funds(
                vpa=p.vpa,
                amount_paise=p.allocated_share_paise,
                reference_id=group.id,
                idempotency_key=ref_key,
                reason=f"Compensating refund: {failure_reason}"
            )
            p.approval_status = ParticipantStatus.REFUNDED.value
            p.refund_transaction_id = ref_res.get("refund_transaction_id")

            op = PaymentProviderOperation(
                group_id=group.id,
                participant_id=p.id,
                operation_type="REFUND",
                idempotency_key=ref_key,
                amount_paise=p.allocated_share_paise,
                status="SUCCESS",
                external_reference=p.refund_transaction_id,
                response_payload=str(ref_res)
            )
            db.add(op)
            await db.commit()

        elif p.approval_status == ParticipantStatus.LOCKED.value and p.lock_id:
            rel_key = f"rel_comp_{group.id}_{p.id}_{p.lock_id}"
            await payment_client.release_funds(
                lock_id=p.lock_id,
                idempotency_key=rel_key,
                reason="Compensating release after group abort"
            )
            p.approval_status = ParticipantStatus.RELEASED.value
            await db.commit()

    group.status = GroupState.ABORTED.value
    await db.commit()
    res_group = await get_group_purchase(db, group.id)
    print(f"DEBUG: res_group.participants count: {len(res_group.participants)}, handles: {[p.user.handle for p in res_group.participants]}")
    return res_group

async def abort_group_purchase(
    db: AsyncSession,
    group_id: str,
    host_user: User,
    reason: str = "Host cancelled purchase"
) -> GroupPurchase:
    """Manually aborts group purchase and releases all holds"""
    group = await get_group_purchase(db, group_id)
    if group.host_user_id != host_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only host can abort.")

    group.status = GroupState.ABORTING.value
    group.failure_reason = reason
    await db.commit()

    for p in group.participants:
        if p.lock_id and p.approval_status == ParticipantStatus.LOCKED.value:
            rel_key = f"rel_abort_{group.id}_{p.id}_{p.lock_id}"
            await payment_client.release_funds(p.lock_id, rel_key, reason=reason)
            p.approval_status = ParticipantStatus.RELEASED.value

    group.status = GroupState.ABORTED.value
    await db.commit()
    res_group = await get_group_purchase(db, group.id)
    print(f"DEBUG: res_group.participants count: {len(res_group.participants)}, handles: {[p.user.handle for p in res_group.participants]}")
    return res_group
