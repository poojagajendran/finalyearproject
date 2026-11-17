from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from simbank.app.core.config import simbank_settings
from simbank.app.core.database import bank_engine, BankBase, BankAsyncSessionLocal
from simbank.app.services.bank_service import seed_bank_accounts
from simbank.app.api.v1.bank import router as bank_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with bank_engine.begin() as conn:
        await conn.run_sync(BankBase.metadata.create_all)
    
    async with BankAsyncSessionLocal() as session:
        await seed_bank_accounts(session)

    yield
    await bank_engine.dispose()

bank_app = FastAPI(
    title="SimBank UPI Gateway Simulator",
    description="Simulated VPA Banking System with Funds-Lock, Atomic Debits, Releases, and HMAC Webhooks",
    version="1.0.0",
    lifespan=lifespan
)

bank_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

bank_app.include_router(bank_router, prefix="/api/v1")

@bank_app.get("/health", tags=["Health"])
async def bank_health():
    return {
        "status": "ok",
        "service": "simbank-gateway",
        "version": "1.0.0"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("simbank.app.main:bank_app", host=simbank_settings.SIMBANK_HOST, port=simbank_settings.SIMBANK_PORT, reload=True)
