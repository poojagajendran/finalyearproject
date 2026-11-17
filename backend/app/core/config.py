import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    APP_ENV: str = "development"
    SECRET_KEY: str = "shopcart-super-secure-production-grade-key-at-least-32-chars-long!"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    COOKIE_NAME: str = "shopcart_token"

    # ShopCart Backend
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    BACKEND_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:3000"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./shopcart.db"
    POSTGRES_DATABASE_URL: Optional[str] = "postgresql+asyncpg://shopcart:shopcart_secret@localhost:5432/shopcart_db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # SimBank Service
    SIMBANK_URL: str = "http://localhost:8001"
    SIMBANK_WEBHOOK_SECRET: str = "simbank-hmac-sha256-webhook-shared-secret-key-shopcart"
    SIMBANK_WEBHOOK_URL: str = "http://localhost:8000/api/v1/payments/webhooks/simbank"

    # Anthropic AI Agent
    ANTHROPIC_API_KEY: str = "mock-key"
    ANTHROPIC_MODEL: str = "claude-3-7-sonnet-20250219"
    MOCK_ANTHROPIC: bool = True

    model_config = {
        "env_file": ".env",
        "extra": "ignore"
    }

settings = Settings()
