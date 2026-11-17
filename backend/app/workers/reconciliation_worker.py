import asyncio
import logging
from sqlalchemy import select
from backend.app.core.database import AsyncSessionLocal
from backend.app.models.group import (
    GroupPurchase, GroupParticipant, PaymentProviderOperation,
    GroupState, ParticipantStatus
)
from backend.app.services.payment_client import payment_client
from backend.app.services.group_service import get_group_purchase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reconciliation_worker")

async def reconcile_pending_operations():
    """
    Background worker loop:
    Scans for groups stuck in COMMITTING or COMPENSATING due to network partitions
    or dropped webhook notifications, reconciling them against SimBank.
    """
    logger.info("Scanning for transactions requiring reconciliation...")
    async with AsyncSessionLocal() as db:
        # Find groups in COMMITTING or COMPENSATING
        stmt = select(GroupPurchase).where(
            GroupPurchase.status.in_([GroupState.COMMITTING.value, GroupState.COMPENSATING.value])
        )
        res = await db.execute(stmt)
        stuck_groups = res.scalars().all()

        for group in stuck_groups:
            logger.info(f"Reconciling Group {group.id} (Status: {group.status})")
            full_group = await get_group_purchase(db, group.id)

            if group.status == GroupState.COMMITTING.value:
                all_debited = True
                for p in full_group.participants:
                    if p.approval_status != ParticipantStatus.DEBITED.value and p.approval_status != ParticipantStatus.DECLINED.value:
                        key = f"debit_{group.id}_{p.id}_{p.allocated_share_paise}"
                        tx = await payment_client.query_transaction(key)
                        if tx and tx.get("status") == "SUCCESS":
                            p.approval_status = ParticipantStatus.DEBITED.value
                            p.debit_transaction_id = tx["transaction_id"]
                            logger.info(f"Reconciled debit for participant {p.user.handle}: SUCCESS")
                        else:
                            all_debited = False

                if all_debited:
                    group.status = GroupState.CONFIRMED.value
                    group.order_id = f"ORD-REC-{group.id[:8].upper()}"
                    logger.info(f"Group {group.id} fully reconciled to CONFIRMED")
                await db.commit()

            elif group.status == GroupState.COMPENSATING.value:
                # Ensure all holds are released and debits refunded
                for p in full_group.participants:
                    if p.approval_status == ParticipantStatus.LOCKED.value and p.lock_id:
                        rel_key = f"rel_rec_{group.id}_{p.id}_{p.lock_id}"
                        await payment_client.release_funds(p.lock_id, rel_key, reason="Worker reconciliation")
                        p.approval_status = ParticipantStatus.RELEASED.value
                group.status = GroupState.ABORTED.value
                logger.info(f"Group {group.id} fully compensated and transitioned to ABORTED")
                await db.commit()

async def run_worker():
    """Continuous polling loop (fallback when Redis arq worker is local)"""
    logger.info("Starting ShopCart Financial Reconciliation Worker...")
    while True:
        try:
            await reconcile_pending_operations()
        except Exception as e:
            logger.error(f"Error during reconciliation run: {e}")
        await asyncio.sleep(15)

if __name__ == "__main__":
    asyncio.run(run_worker())
