import json
from datetime import datetime, timezone
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from simbank.app.core.config import simbank_settings
from simbank.app.core.security import generate_signature
from simbank.app.models.bank import BankWebhookLog

async def dispatch_webhook(
    db: AsyncSession,
    event_type: str,
    reference_id: str,
    payload: dict,
    target_url: str = simbank_settings.SIMBANK_WEBHOOK_URL
) -> bool:
    """
    Dispatches HMAC-SHA256 signed webhook to ShopCart backend.
    Logs delivery attempt and status code to BankWebhookLog.
    """
    payload_with_meta = {
        **payload,
        "event_type": event_type,
        "reference_id": reference_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    payload_bytes = json.dumps(payload_with_meta, sort_keys=True).encode("utf-8")
    signature = generate_signature(payload_bytes, simbank_settings.SIMBANK_WEBHOOK_SECRET)

    headers = {
        "Content-Type": "application/json",
        "X-SimBank-Signature": signature,
        "X-SimBank-Event": event_type
    }

    delivered = False
    status_code = None

    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            res = await client.post(target_url, content=payload_bytes, headers=headers)
            status_code = res.status_code
            delivered = (res.status_code in [200, 201, 202, 204])
    except Exception:
        delivered = False
        status_code = 503

    log_entry = BankWebhookLog(
        event_type=event_type,
        reference_id=reference_id,
        payload_json=json.dumps(payload_with_meta),
        signature=signature,
        delivered=delivered,
        status_code=status_code
    )
    db.add(log_entry)
    await db.commit()

    return delivered
