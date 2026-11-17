from pydantic_settings import BaseSettings

class SimBankSettings(BaseSettings):
    APP_ENV: str = "development"
    SIMBANK_HOST: str = "0.0.0.0"
    SIMBANK_PORT: int = 8001
    
    # Standalone SimBank database (isolated from ShopCart)
    DATABASE_URL: str = "sqlite+aiosqlite:///./simbank.db"
    
    # Shared secret for signing webhooks with HMAC-SHA256
    SIMBANK_WEBHOOK_SECRET: str = "simbank-hmac-sha256-webhook-shared-secret-key-shopcart"
    SIMBANK_WEBHOOK_URL: str = "http://localhost:8000/api/v1/payments/webhooks/simbank"

    model_config = {
        "env_file": ".env",
        "extra": "ignore"
    }

simbank_settings = SimBankSettings()
