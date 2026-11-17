import hmac
import hashlib
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from simbank.app.core.config import simbank_settings

ph = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)

def hash_pin(pin: str) -> str:
    """Hash numeric UPI PIN using Argon2id"""
    return ph.hash(str(pin))

def verify_pin(plain_pin: str, hashed_pin: str) -> bool:
    """Verify numeric UPI PIN"""
    try:
        return ph.verify(hashed_pin, str(plain_pin))
    except (VerifyMismatchError, Exception):
        return False

def generate_signature(payload_bytes: bytes, secret: str = simbank_settings.SIMBANK_WEBHOOK_SECRET) -> str:
    """Generate HMAC-SHA256 signature for webhook payload"""
    return hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()

def verify_signature(payload_bytes: bytes, signature: str, secret: str = simbank_settings.SIMBANK_WEBHOOK_SECRET) -> bool:
    """Verify incoming HMAC-SHA256 signature with constant-time comparison"""
    expected = generate_signature(payload_bytes, secret)
    return hmac.compare_digest(expected, signature)
