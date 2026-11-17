import httpx
from typing import Optional, Dict, Any
from fastapi import HTTPException, status
from backend.app.core.config import settings

class PaymentClient:
    """
    HTTP client for SimBank Payment Gateway.
    Executes outside database transactions to avoid holding connection locks.
    """
    def __init__(self, base_url: str = settings.SIMBANK_URL, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.base_url = base_url.rstrip("/")
        self.transport = transport

    def _get_client(self, timeout: float = 8.0) -> httpx.AsyncClient:
        if self.transport is not None:
            return httpx.AsyncClient(transport=self.transport, base_url=self.base_url, timeout=timeout)
        return httpx.AsyncClient(timeout=timeout)

    async def lock_funds(
        self,
        vpa: str,
        pin: str,
        amount_paise: int,
        reference_id: str,
        idempotency_key: str
    ) -> Dict[str, Any]:
        """Locks funds in participant's bank account via SimBank"""
        url = f"{self.base_url}/api/v1/bank/locks"
        payload = {
            "vpa": vpa,
            "pin": pin,
            "amount_paise": amount_paise,
            "reference_id": reference_id,
            "idempotency_key": idempotency_key
        }
        try:
            async with self._get_client(timeout=8.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code in [200, 201]:
                    return res.json()
                detail = res.json().get("detail", "Bank funds-lock failed")
                raise HTTPException(status_code=res.status_code, detail=detail)
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="SimBank lock operation timed out. Reconciliation required."
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Unable to contact SimBank gateway: {str(e)}"
            )

    async def debit_funds(
        self,
        lock_id: str,
        amount_paise: int,
        reference_id: str,
        idempotency_key: str
    ) -> Dict[str, Any]:
        """Debits previously locked funds"""
        url = f"{self.base_url}/api/v1/bank/debits"
        payload = {
            "lock_id": lock_id,
            "amount_paise": amount_paise,
            "reference_id": reference_id,
            "idempotency_key": idempotency_key
        }
        try:
            async with self._get_client(timeout=8.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    return res.json()
                detail = res.json().get("detail", "Bank debit failed")
                raise HTTPException(status_code=res.status_code, detail=detail)
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="SimBank debit operation timed out. Reconciliation required."
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Unable to reach SimBank for debit: {str(e)}"
            )

    async def release_funds(
        self,
        lock_id: str,
        idempotency_key: str,
        reason: str = "Order cancelled or resplit"
    ) -> Dict[str, Any]:
        """Releases hold on bank funds"""
        url = f"{self.base_url}/api/v1/bank/releases"
        payload = {
            "lock_id": lock_id,
            "idempotency_key": idempotency_key,
            "reason": reason
        }
        try:
            async with self._get_client(timeout=8.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    return res.json()
                return {"status": "ERROR", "detail": res.text}
        except Exception as e:
            return {"status": "FAILED", "detail": str(e)}

    async def refund_funds(
        self,
        vpa: str,
        amount_paise: int,
        reference_id: str,
        idempotency_key: str,
        reason: str = "Compensating refund"
    ) -> Dict[str, Any]:
        """Sends compensating refund back to participant bank account"""
        url = f"{self.base_url}/api/v1/bank/refunds"
        payload = {
            "vpa": vpa,
            "amount_paise": amount_paise,
            "reference_id": reference_id,
            "idempotency_key": idempotency_key,
            "reason": reason
        }
        try:
            async with self._get_client(timeout=8.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    return res.json()
                return {"status": "ERROR", "detail": res.text}
        except Exception as e:
            return {"status": "FAILED", "detail": str(e)}

    async def query_transaction(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        """Queries transaction by idempotency key to resolve ambiguous network timeouts"""
        url = f"{self.base_url}/api/v1/bank/transactions/by-key/{idempotency_key}"
        try:
            async with self._get_client(timeout=5.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    return res.json()
                return None
        except Exception:
            return None

payment_client = PaymentClient()
