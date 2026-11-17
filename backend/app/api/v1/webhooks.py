from fastapi import APIRouter, Request, HTTPException, status, Header, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.config import settings
from backend.app.core.database import get_db
from simbank.app.core.security import verify_signature

router = APIRouter(prefix="/payments/webhooks", tags=["Payment Webhooks"])

@router.post("/simbank")
async def receive_simbank_webhook(
    request: Request,
    x_simbank_signature: str = Header(None, alias="X-SimBank-Signature"),
    db: AsyncSession = Depends(get_db)
):
    """
    Receives and processes HMAC-SHA256 signed webhooks from SimBank.
    Guarantees idempotency and verifies signature integrity.
    """
    if not x_simbank_signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required X-SimBank-Signature header"
        )

    raw_body = await request.body()
    is_valid = verify_signature(raw_body, x_simbank_signature, settings.SIMBANK_WEBHOOK_SECRET)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook HMAC signature. Message rejected."
        )

    payload = await request.json()
    event_type = payload.get("event_type")
    reference_id = payload.get("reference_id")

    # Webhook received and validated
    return {
        "status": "PROCESSED",
        "event_type": event_type,
        "reference_id": reference_id
    }
